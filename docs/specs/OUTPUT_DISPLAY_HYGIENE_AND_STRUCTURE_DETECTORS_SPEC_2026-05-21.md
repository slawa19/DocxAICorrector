# Output Display Hygiene And Structure Detectors Spec

Date: 2026-05-21
Status: Proposed; ready for implementation after approval
Parent specs:

- `docs/AI_FIRST_STRUCTURE_RECOVERY_SPEC_2026-05-08.md`
- `docs/specs/TOPOLOGY_FIRST_STRUCTURE_RECOVERY_REMEDIATION_SPEC_2026-05-12.md`
- `docs/specs/LAYOUT_SIGNAL_EVIDENCE_SLICE_SPEC_2026-05-14.md`
- Companion upstream spec:
  `docs/specs/STRUCTURE_RECOGNITION_INPUT_FIDELITY_SPEC_2026-05-21.md`

## Summary

Add a narrow final-output safety layer that separates non-semantic display
hygiene from structural quality detection.

This spec intentionally does **not** introduce a new Markdown structural
postprocessor. It adds:

1. `MarkdownDisplayHygienePostPass`: a deterministic, diagnostics-heavy cleanup
   for explicit PDF page-furniture noise only.
2. `StructureQualityDetectors`: read-only detectors that make reader-visible
   structural defects fail or warn through acceptance checks without rewriting
   Markdown.

The central rule is:

```text
Display hygiene may remove page-furniture text only when the removed span is
classified as non-semantic output noise. It must not create, delete, merge,
split, promote, demote, or rename Markdown headings. Any defect requiring such
an operation is a structural defect and must be exposed through detectors, not
repaired by this post-pass.
```

## Problem

The current real-document acceptance gate is strong at checking pipeline
success, DOCX openability, mapping drift, heading-level drift, text similarity,
and selected structural proxy conditions. It is weak at reader-visible output
hygiene and malformed final Markdown structure.

Observed output-quality defects can pass acceptance when they do not break
mapping or similarity counts, for example:

- blank-page markers leaking into body text;
- page numbers or running headers leaking inline;
- adjacent H1 headings with no body between them;
- Markdown headings concatenated with the first body sentence;
- epigraph or attribution-like text rendered as H1.

Some of these defects are display hygiene. Others are structural defects. The
pipeline must not hide that distinction by adding regex-based structural rewrites
in final Markdown.

## Architectural Position

This spec is a compatibility and observability slice at the late output stage.
It does not change the authority model from the parent specs.

Allowed authority:

- final Markdown display cleanup for confirmed page-furniture noise;
- read-only quality metrics and acceptance checks over final Markdown;
- diagnostics artifacts with rule hits and samples.

Forbidden authority:

- assigning final roles;
- assigning or changing final heading levels;
- merging adjacent headings;
- splitting headings from body sentences;
- demoting H1/H2/H3 to paragraph or blockquote;
- using document-derived phrase expansion as a new structure recognizer;
- treating Markdown detectors as topology authority.

This spec deliberately complements the parent spec's `R3 Markdown Postprocessor
Retirement Plan`: structural Markdown postprocessors should retire, while
non-structural display hygiene may remain only when explicitly scoped and
separated from structural readiness authority.

## Upstream Structure Responsibility

This spec is not the primary owner for PDF-furniture structural recovery. The
primary owner is Stage 1 `DocumentMap` input fidelity: deterministic signals must
expose page-furniture contamination to the model, and `DocumentMap` must return
split hints or review zones when globally supported.

Display hygiene remains a final safety net for non-semantic residue only. It
must not compensate for missing Stage 1 descriptor signals by broadening final
Markdown cleanup.

The deterministic page-furniture detection library must be the single source of
truth. The shared phrase list and related matching helpers currently rooted in
`src/docxaicorrector/structure/topology.py` must be extracted before duplicate
phrase lists are added. Stage 1 descriptor hint construction, topology candidate
operations, display hygiene, and output detectors must consume the same library.

## Goals

1. Remove a small, curated class of non-semantic page-furniture noise from final
   Markdown before DOCX formatting transfer.
2. Make reader-visible structural defects visible in acceptance reports.
3. Preserve the AI-first / topology-first boundary: structural defects fail or
   warn, but are not repaired by final Markdown regexes.
4. Persist enough diagnostics to review every cleanup and every detector hit.
5. Keep rollout profile-gated so existing profiles can collect metrics before
   strict failure thresholds are enabled.

## Non-Goals

- No Stage 1 prompt change.
- No Stage 1 schema change.
- No Stage 2 descriptor or classifier change.
- No Stage 3 reconciliation change.
- No `DocumentMap` or `DocumentTopologyProjection` authority expansion.
- No automatic Markdown fix for adjacent H1, heading/body concat, or epigraph
  attribution headings.
- No table detection, footnote policy, typography policy, AI rewriting, or style
  aesthetics.
- No on-the-fly expansion of the blank-page phrase library from document body
  text.
- No replacement of existing topology-side `candidate_page_artifact_split`
  diagnostics.
- No replacement for `DocumentMap` input-fidelity improvements.
- No attempt to compensate for missing Stage 1 descriptor signals by broadening
  final Markdown cleanup.

## Current State Evidence

Late-phase output code currently imports and applies Markdown normalizers from
`src/docxaicorrector/pipeline/output_validation.py` in
`src/docxaicorrector/pipeline/late_phases.py`, including:

- `normalize_page_placeholder_heading_concats_markdown`
- `normalize_false_fragment_headings_markdown`
- `normalize_residual_bullet_glyphs_markdown`
- `normalize_list_fragment_regressions_markdown`
- `normalize_mixed_script_markdown`

The parent remediation spec records that structural Markdown postprocessors are
transitional compatibility cleanup and should stop acting as readiness authority.
This spec narrows the allowed late-output behavior to display hygiene and
read-only detectors.

`src/docxaicorrector/validation/structural.py` already builds acceptance checks
in `_build_structural_checks(...)`. It has the correct integration point for new
profile-gated checks, but it currently has no dedicated checks for blank-page
marker leakage, inline page furniture leakage, adjacent H1 without body,
heading/body concatenation, or H1 epigraph attribution shape.

## Design Overview

```text
final markdown assembled
  -> StructureQualityDetectors collect raw detector metrics       # read-only
  -> MarkdownDisplayHygienePostPass removes confirmed noise       # R1, R2-narrow only
  -> StructureQualityDetectors collect cleaned detector metrics   # read-only
  -> display_hygiene_report persisted
  -> formatting_transfer / DOCX build consumes cleaned markdown
  -> structural acceptance reads detector metrics and thresholds
```

The detector layer must be callable without the cleanup layer. The implementation
order therefore starts with detectors and acceptance plumbing before any cleanup
behavior changes.

## New Module

Add a new module:

`src/docxaicorrector/pipeline/display_hygiene.py`

The module must be pure Python and must not call AI, external commands, DOCX
rendering, or filesystem APIs except through an explicit artifact writer helper.

Recommended public API:

```python
from dataclasses import dataclass
from typing import Literal

DisplayHygieneRuleId = Literal[
    "blank_page_marker",
    "inline_page_furniture",
]

StructureDetectorId = Literal[
    "pdf_blank_page_marker_leakage",
    "inline_page_furniture_leakage",
    "adjacent_h1_without_body",
    "heading_body_concat_detected",
    "h1_epigraph_attribution_pattern",
]

@dataclass(frozen=True)
class DisplayHygieneSample:
    rule_id: str
    line: int
    column: int | None
    removed_text: str
    original_line: str
    normalized_line: str
    reason: str
    confidence: str

@dataclass(frozen=True)
class StructureDetectorSample:
    detector_id: str
    line: int
    heading_level: int | None
    text: str
    previous_context: str
    next_context: str
    reason: str

@dataclass(frozen=True)
class DisplayHygieneReport:
    schema_version: int
    run_id: str | None
    input_sha256: str
    output_sha256: str
    changed: bool
    heading_inventory_preserved: bool
    rule_counts: dict[str, int]
    detector_counts_raw: dict[str, int]
    detector_counts_cleaned: dict[str, int]
    samples: tuple[DisplayHygieneSample, ...]
    detector_samples_raw: tuple[StructureDetectorSample, ...]
    detector_samples_cleaned: tuple[StructureDetectorSample, ...]


def collect_structure_quality_detector_samples(markdown: str) -> tuple[StructureDetectorSample, ...]: ...


def apply_markdown_display_hygiene_postpass(
    markdown: str,
    *,
    run_id: str | None = None,
    max_samples_per_rule: int = 20,
) -> tuple[str, DisplayHygieneReport]: ...
```

Implementation may split this into smaller internal dataclasses, but the emitted
artifact must preserve the fields above or their direct equivalents.

## Artifact Contract

Persist display hygiene diagnostics under:

`.run/display_hygiene_reports/<run_id>.json`

Use the same retention style as existing `.run/..._reports` directories.
Implementation should use the existing runtime artifact retention utility if
available in the target code path.

Artifact JSON shape:

```json
{
  "schema_version": 1,
  "run_id": "20260521T141353Z_example",
  "input_sha256": "...",
  "output_sha256": "...",
  "changed": true,
  "heading_inventory_preserved": true,
  "rule_counts": {
    "blank_page_marker": 2,
    "inline_page_furniture": 0
  },
  "detector_counts_raw": {
    "pdf_blank_page_marker_leakage": 2,
    "inline_page_furniture_leakage": 1,
    "adjacent_h1_without_body": 0,
    "heading_body_concat_detected": 0,
    "h1_epigraph_attribution_pattern": 0
  },
  "detector_counts_cleaned": {
    "pdf_blank_page_marker_leakage": 0,
    "inline_page_furniture_leakage": 1,
    "adjacent_h1_without_body": 0,
    "heading_body_concat_detected": 0,
    "h1_epigraph_attribution_pattern": 0
  },
  "samples": [
    {
      "rule_id": "blank_page_marker",
      "line": 42,
      "column": 1,
      "removed_text": "This page intentionally left blank",
      "original_line": "This page intentionally left blank",
      "normalized_line": "",
      "reason": "standalone_blank_page_marker",
      "confidence": "high"
    }
  ],
  "detector_samples_raw": [],
  "detector_samples_cleaned": []
}
```

Line numbers are 1-based and must refer to the Markdown string passed into the
corresponding raw or cleaned detector pass. `samples` may be truncated by
`max_samples_per_rule`, but `rule_counts` and `detector_counts_*` must count all
hits.

## Layer 1: MarkdownDisplayHygienePostPass

### Insertion Point

Call the post-pass inside `src/docxaicorrector/pipeline/late_phases.py` in the
DOCX build path after final Markdown is assembled and before formatting transfer
or DOCX conversion consumes that Markdown.

The post-pass must operate on the same final Markdown that is intended for user
visible DOCX output, not on intermediate structural Markdown unless the caller
explicitly records the input kind in diagnostics.

### Heading Inventory Invariant

The cleanup layer must preserve Markdown heading inventory.

Define heading inventory as the ordered tuple of all Markdown ATX heading lines:

```text
(level, normalized_heading_text)
```

where `level` is the number of leading `#` characters and
`normalized_heading_text` trims leading/trailing spaces and collapses internal
whitespace after removing only the Markdown heading marker.

Required invariant:

```text
heading_inventory(before) == heading_inventory(after)
```

If the invariant fails, the post-pass must fail closed:

- return the original Markdown unchanged;
- emit `heading_inventory_preserved = false`;
- record an error diagnostic in the report;
- do not persist a rewritten Markdown as successful display hygiene.

Unit tests must cover this invariant.

### Rule R1: Blank Page Marker Removal

Rule id: `blank_page_marker`

Purpose: remove explicit blank-page furniture from final Markdown when it is
clearly non-semantic output noise.

Closed phrase library, initial entries:

```python
BLANK_PAGE_MARKER_PHRASES = frozenset(
    {
        "this page intentionally left blank",
        "page intentionally left blank",
        "intentionally blank",
        "intentionally left blank",
        "эта страница намеренно оставлена пустой",
    }
)
```

This initial library must match the shared page-furniture library extracted by
`docs/specs/STRUCTURE_RECOGNITION_INPUT_FIDELITY_SPEC_2026-05-21.md` Phase 0.
Do not expand the output-only phrase set ahead of the shared library.

Adding a phrase requires updating the shared library contract in the upstream
spec or a follow-up spec and adding round-trip tests that prove the new phrase
is safe across Stage 1 descriptor hints, topology candidate operations, display
hygiene, and output detectors.

Allowed removal shapes:

1. Standalone line: the normalized line equals a phrase, optionally followed by
   punctuation `.` / `:` / `;`.
2. Markdown paragraph inline island: the normalized paragraph contains only the
   phrase plus punctuation and surrounding whitespace.
3. Page-furniture concat island: the phrase appears at the start of a line,
   followed by a short page-number/header island and then body text or heading
   text. Only the phrase and confirmed page-furniture island may be removed; the
   remaining semantic text must stay in the same order.

R1 must not remove text when the phrase appears inside:

- fenced code blocks;
- blockquote lines starting with `>`;
- Markdown headings;
- long prose sentences that quote or discuss the phrase;
- inline code spans;
- lines where removing the phrase would change a heading line.

R1 diagnostics:

- `line`
- `column`
- `removed_text`
- `original_line`
- `normalized_line`
- `reason` in a closed set:
  - `standalone_blank_page_marker`
  - `paragraph_blank_page_marker`
  - `blank_page_marker_with_page_furniture`
- `confidence = "high"`

### Rule R2-Narrow: Inline Page Furniture Removal

Rule id: `inline_page_furniture`

Purpose: remove only high-confidence inline page numbers / running headers that
remain after assembly.

R2 is intentionally narrow and diagnostic-first. A candidate must be reported
when it looks suspicious. It may be removed only when all cleanup guards pass.

Candidate shape:

- a short inline island with `<= 4` tokens;
- contains a page number token shaped as either:
  - Arabic integer: `1` through `9999`, optionally surrounded by punctuation;
  - Roman numeral: `i` through `xxxix`, case-insensitive;
- contains at least one neighboring text token that is repeated elsewhere in the
  document as a likely running-header token.

Cleanup guards, all required:

1. The candidate island has `<= 4` tokens after punctuation stripping.
2. Exactly one token is a page-number shape.
3. At least one non-number neighbor token appears in a repeated-header index with
   document frequency `>= 3` on distinct lines.
4. The candidate is close to page furniture: same line as an R1 blank-page marker
   hit, adjacent to a line with an R1 hit, or matches an already-known page
   furniture phrase from the closed library.
5. Removing the island does not alter heading inventory.
6. Removing the island does not create an empty non-whitespace heading or list
   marker.

If any guard fails, R2 must not remove the candidate. It should still be counted
by `inline_page_furniture_leakage` if the detector identifies it.

R2 diagnostics:

- `line`
- `column`
- `removed_text`
- `original_line`
- `normalized_line`
- `reason = "guarded_inline_page_furniture"`
- `confidence = "high"`

The repeated-header index is a local document statistic used only to validate
candidate deletion. It must not be used to synthesize new phrases, new headings,
or structural regions.

## Layer 2: StructureQualityDetectors

The detector layer is read-only. It takes Markdown and returns counts plus
samples. It must never modify Markdown.

All detectors should expose:

- total count;
- first N samples, default 20;
- 1-based line number;
- nearby context;
- closed reason string.

### Detector D1: `pdf_blank_page_marker_leakage`

Counts remaining blank-page marker phrases from the R1 closed phrase library.

Detection must use the same safe scanning exclusions as R1:

- ignore fenced code blocks;
- ignore inline code spans;
- ignore blockquotes that quote the phrase;
- ignore Markdown headings.

Default strict threshold for real-document profiles: `0`.

### Detector D2: `inline_page_furniture_leakage`

Counts suspicious inline page-furniture candidates that R2 did not remove or was
not configured to remove.

This detector should be broader than R2 cleanup but still conservative:

- line contains a page-number shaped token;
- neighboring token repeats as a running-header candidate `>= 3` times;
- the candidate is short and visually island-like;
- ignore index/table-of-contents page ranges and bibliography-like numeric
  citations where possible.

Default threshold should be profile-configurable. Recommended initial strict
thresholds:

- full-book PDF profiles: `<= 0` only after baseline review;
- focused real-document profiles: `<= 0` when page-furniture defects are in
  scope;
- generic profiles: advisory metrics only at first rollout.

### Detector D3: `adjacent_h1_without_body`

Counts pairs of adjacent H1 headings with no non-empty body content between them.

Markdown definition:

- H1 line matches `^#\s+\S`;
- ignore blank lines between headings;
- ignore HTML comments and known internal placeholders if present;
- if the next non-blank semantic line is another H1, count one defect.

This detector does not decide which heading is correct. It only reports the
malformed shape.

Default strict threshold for structure-sensitive real-document profiles: `0`.

### Detector D4: `heading_body_concat_detected`

Counts Markdown heading lines that appear to include the first sentence of body
text.

Candidate signal:

- line is an ATX heading `#{1,6}`;
- heading text has more than `HEADING_BODY_CONCAT_MAX_WORDS = 18` words, or more
  than `HEADING_BODY_CONCAT_MAX_CHARS = 140` characters;
- heading text contains sentence punctuation followed by a lowercase/body-like
  continuation, or contains two sentence-like clauses;
- heading does not match accepted long-title shapes.

Accepted long-title shapes should be conservative and closed:

- title ending with `:`;
- title case / all caps long title with no terminal sentence punctuation;
- numbered appendix/index headings;
- scripture/reference headings already accepted by existing validation helpers.

Default threshold should be profile-configurable. Recommended initial value for
strict PDF profiles: `0` or a small explicit budget after baseline review.

### Detector D5: `h1_epigraph_attribution_pattern`

Counts H1 headings that look like epigraph attribution or attribution-only text.

This detector must not use a list of personal names. It should use attribution
shape only.

Candidate shapes:

- H1 text starts with an attribution dash: `-- Name, role` or `— Name, role`;
- H1 text ends with an attribution clause after a quote-like line;
- H1 text is short and matches `Name, role/title/affiliation` with no chapter
  tokens and no numbering.

Recommended chapter-token exclusion examples:

- `chapter`
- `глава`
- `part`
- `section`
- Arabic or Roman chapter numbering near the start

The detector reports suspicious H1 attribution shape. It does not demote the
heading.

Default threshold for structure-sensitive real-document profiles: `0` after
baseline review. Generic profiles should start advisory.

## Acceptance Integration

Add detector metrics to structural validation metrics before
`_build_structural_checks(...)` appends checks.

Recommended metric keys:

```python
"pdf_blank_page_marker_leakage_count"
"inline_page_furniture_leakage_count"
"adjacent_h1_without_body_count"
"heading_body_concat_detected_count"
"h1_epigraph_attribution_pattern_count"
"display_hygiene_report_path"
"display_hygiene_rule_counts"
"display_hygiene_heading_inventory_preserved"
```

Add profile-gated checks in `src/docxaicorrector/validation/structural.py`:

```python
{
    "name": "pdf_blank_page_marker_leakage",
    "passed": actual <= allowed,
    "actual": actual,
    "allowed": allowed,
    "samples": samples,
}
```

Equivalent checks:

- `pdf_blank_page_marker_leakage`
- `inline_page_furniture_leakage`
- `adjacent_h1_without_body`
- `heading_body_concat_detected`
- `h1_epigraph_attribution_pattern`

### Profile Fields

Add optional fields to `DocumentProfile` and `corpus_registry.toml` parsing:

```python
max_pdf_blank_page_marker_leakage: int | None = None
max_inline_page_furniture_leakage: int | None = None
max_adjacent_h1_without_body: int | None = None
max_heading_body_concat_detected: int | None = None
max_h1_epigraph_attribution_pattern: int | None = None
```

Semantics:

- `None`: collect metrics and samples, but do not add a failing acceptance check.
- integer: add the acceptance check and require `actual <= threshold`.

This keeps rollout safe. Strict profiles can opt in immediately. Generic profiles
can observe metrics before becoming strict.

### Expected Failed Checks During Rollout

For profiles that intentionally become red after detector rollout, update
`structural_expected_failed_checks` or profile-specific expectation metadata
explicitly. Do not hide new detector failures by raising thresholds without a
recorded rationale.

## Late-Phase Reporting Integration

`late_phases.py` should expose the display hygiene report path and detector
counts through the existing docx-phase / quality-report payloads so structural
validation can consume them without rescanning when possible.

If both a persisted report and direct Markdown are available, direct Markdown
scanning is the source of truth for the current run. Persisted reports are
supporting diagnostics.

Required log event:

```json
{
  "event_id": "display_hygiene_report_saved",
  "context": {
    "artifact_path": ".run/display_hygiene_reports/<run_id>.json",
    "changed": true,
    "rule_counts": {"blank_page_marker": 2},
    "detector_counts_cleaned": {"pdf_blank_page_marker_leakage": 0},
    "heading_inventory_preserved": true
  }
}
```

## Implementation Plan

Before enabling strict structural detector thresholds broadly, run the input
fidelity diagnostic package from
`docs/specs/STRUCTURE_RECOGNITION_INPUT_FIDELITY_SPEC_2026-05-21.md` so failures
can be attributed to missing Stage 1 signals versus late display residue.

## Current Strategic Recommendation

At the current project stage, this package should be treated as a narrow
late-output hygiene and observability layer, not as the primary roadmap for more
structure-first complexity.

Recommended priority order:

1. keep detector logic useful for observability and artifact review;
2. keep cleanup limited to deterministic non-semantic display hygiene;
3. avoid turning new detector counts into broad full-book blockers too early;
4. use the outcome of `docs/specs/SIMPLE_READER_FIRST_MVP_SPEC_2026-05-21.md` as
   the main decision gate for broader rollout.

Reason:

- if the reader-first MVP shows materially better reader-visible artifacts with a
  simpler pipeline, this spec should support that outcome as shared hygiene
  infrastructure rather than expand structure-first governance;
- if the reader-first MVP does **not** materially outperform the current path,
  then the detector/cleanup layer defined here becomes a stronger candidate for
  gradual rollout inside the existing structure-first pipeline.

Current recommendation by phase:

- Phase 0 detector-only plumbing: good immediate value;
- Phase 1 R1 blank-page cleanup: good immediate value if heading inventory stays
  preserved;
- Phase 2 R2-narrow inline page furniture cleanup: useful, but keep conservative
  and diagnostic-heavy;
- Phase 3 strict profile rollout: defer broad activation until reader-first MVP
  evidence is reviewed.

## Reader-First Decision Gate

Before enabling strict detector thresholds broadly, compare this package against
the future outcome of `docs/specs/SIMPLE_READER_FIRST_MVP_SPEC_2026-05-21.md`.

Use the MVP outcome to choose one of these paths:

1. Reader-first wins clearly.

   Then:

   - keep this spec's R1/R2 deterministic cleanup and report artifacts as shared
     late-output infrastructure;
   - keep D3/D4/D5 mostly as observability/report signals;
   - do not expand this package into a new structure-first governance layer.

2. Reader-first and structure-first are mixed, but both benefit from the same
   deterministic display cleanup.

   Then:

   - promote R1/R2 as shared output hygiene for both paths;
   - keep thresholds advisory for benchmark/full-book profiles until repeated
     evidence shows the detector is high-signal and low-noise.

3. Reader-first does not improve the reader-visible result enough to justify a
   pivot.

   Then:

   - continue with cautious rollout of this spec inside structure-first;
   - enable thresholds only per profile and only after baseline artifacts are
     reviewed.

Until that decision gate is resolved, benchmark-only full-book profiles should
prefer detector metrics and saved samples over new fail-fast policy wherever
possible.

Cross-spec prerequisite order:

1. Extract the shared page-furniture detection library from the companion input
   fidelity spec Phase 0.
2. Land detector-only output plumbing from this spec.
3. Land Stage 1 descriptor signals / preview / diagnostics from the companion
   spec before tightening output thresholds.

### Phase 0: Detector-Only Plumbing

Files likely affected:

- `src/docxaicorrector/pipeline/display_hygiene.py`
- `src/docxaicorrector/validation/structural.py`
- `src/docxaicorrector/validation/profiles.py`
- `tests/test_output_display_hygiene.py` or equivalent
- `tests/test_real_document_validation_corpus.py` for profile/check plumbing

Work:

1. Implement `collect_structure_quality_detector_samples(...)`.
2. Add metric extraction for detector counts and samples.
3. Add optional `DocumentProfile` threshold fields.
4. Add profile-gated acceptance checks.
5. Keep all checks advisory unless the profile sets a threshold.
6. Depend on the extracted shared page-furniture detector library; do not create
   a second phrase list inside the output pipeline.

Acceptance:

- Unit tests cover all five detectors.
- A profile with thresholds emits failing checks when samples exist.
- A profile with `None` thresholds records metrics without failing.
- No Markdown output changes.

### Phase 1: R1 Blank Page Marker Cleanup

Files likely affected:

- `src/docxaicorrector/pipeline/display_hygiene.py`
- `src/docxaicorrector/pipeline/late_phases.py`
- display hygiene report writer / retention helper
- tests for late-phase report passthrough

Work:

1. Implement R1 with the closed phrase library.
2. Add heading inventory invariant and fail-closed behavior.
3. Persist `.run/display_hygiene_reports/<run_id>.json`.
4. Wire post-pass before formatting transfer.
5. Add `display_hygiene_report_saved` log event.
6. Continue using the shared page-furniture detector library introduced by the
   companion input-fidelity spec; no local phrase-list fork is allowed.

Acceptance:

- Standalone RU/EN blank-page marker lines are removed.
- Blockquote/code/heading/prose quotation cases are not removed.
- Heading inventory is preserved.
- If a simulated cleanup changes heading inventory, original Markdown is
  returned unchanged and report records failure.
- `pdf_blank_page_marker_leakage` drops after cleanup in a targeted fixture.

### Phase 2: R2-Narrow Inline Page Furniture Cleanup

Work:

1. Implement repeated-header candidate index.
2. Implement R2 candidate detection and cleanup guards.
3. Count unremoved candidates through `inline_page_furniture_leakage`.
4. Add tests for false positives: indexes, TOC page ranges, citations, years,
   numbered list items, and legal short headings.

Acceptance:

- R2 removes only candidates satisfying all guards.
- R2 does not remove legal index/TOC/page-range content.
- R2 does not alter heading inventory.
- R2 leaves uncertain candidates in place and reports them as detector samples.

### Phase 3: Real-Document Profile Rollout

Profiles to run and review:

- `lietaer-core`
- `lietaer-pdf-full-benchmark`
- `end-times-pdf-core`
- Lietaer chapter 1 / first-chapter profile used by the current registry

Rollout rule:

- If R1/R2 remove legal text, narrow the phrase library or guards.
- Do not expand cleanup rules to make a profile green.
- If R3/R4/R5 detectors fail, record them as structural follow-up work for a
  topology-side spec.

## Test Plan

Unit tests:

- R1 removes standalone English blank marker.
- R1 removes standalone Russian blank marker.
- R1 ignores fenced code and inline code.
- R1 ignores blockquote quotations.
- R1 ignores Markdown headings.
- R1 does not remove long prose sentences discussing the phrase.
- R1 preserves heading inventory.
- R2 removes only all-guards-pass page furniture.
- R2 leaves candidate when repeated-header frequency is below threshold.
- R2 leaves candidate when no page-furniture proximity exists.
- D3 counts adjacent H1 with only blank lines between them.
- D3 does not count H1 separated by body text.
- D4 counts heading/body concatenation.
- D4 ignores accepted long-title shapes.
- D5 counts attribution-shaped H1 without name allowlists.
- D5 ignores chapter-token H1 headings.

Integration tests:

- `late_phases` writes `display_hygiene_report_saved` event when cleanup runs.
- structural validation includes detector metrics in report payload.
- profile thresholds produce the expected failed check names.
- advisory profiles collect metrics without failing.

Canonical verification after implementation:

```bash
bash scripts/test.sh tests/test_output_display_hygiene.py -vv
bash scripts/test.sh tests/test_real_document_validation_corpus.py -vv -x
bash scripts/test.sh tests/ -q
```

For real-document profile verification, follow `AGENTS.md` runtime rules and use
the canonical WSL entrypoints or VS Code tasks. Full-book profile runs are
milestones, not an inner-loop tuning mechanism.

## Safety And Failure Modes

Fail closed:

- If heading inventory changes, return original Markdown unchanged.
- If cleanup raises unexpectedly, return original Markdown unchanged and record a
  report error when possible.
- If artifact writing fails, do not fail the pipeline solely because diagnostics
  could not be persisted; log the error and continue with in-memory metrics.

Do not silently pass:

- If detector counts exceed profile thresholds, acceptance must include the
  failed check name.
- If cleanup removed text, samples must exist unless sample truncation is set to
  zero intentionally in tests.

## Future Work

R3/R4/R5-class defects exposed by this spec should be handled first through
`docs/specs/STRUCTURE_RECOGNITION_INPUT_FIDELITY_SPEC_2026-05-21.md` and then,
where needed, through separate topology-side remediation specs. Follow-up work
must use `DocumentMap` / `DocumentTopologyProjection` authority or another
explicitly approved topology contract, not final Markdown regex rewrites.

Possible follow-up packages:

- topology-side handling for adjacent H1 without body;
- structure-aware heading/body boundary repair;
- AI/topology-authorized epigraph and attribution classification;
- structural-unit renderer that reduces need for Markdown compatibility cleanup.
