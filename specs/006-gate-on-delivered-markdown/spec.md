# Feature Specification: Production gate measures the delivered markdown

Date: 2026-07-11
Status: ACTIVE forward spec
Owner surface: `_build_translation_quality_report` — the hygiene/structural REPORTING metrics
Companion: `specs/005-hygiene-pass-safety/spec.md` (increment C); `specs/001`/`003` (source-aware structural gates);
`docs/specs/GATE_TRUSTWORTHINESS_AND_UI_DATA_REFACTOR_2026-07-09.md` (blocker 6). Increment B of the two-markdown
convergence.
Changelog:
- 2026-07-11 — Created from the two-markdown architecture audit. Reframed: the harness ALREADY measures the
  delivered markdown; this aligns production with it.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - The report's hygiene counts describe the delivered document (Priority: P1)

The report's residual-glyph / mixed-script / page-placeholder / bullet-heading counts reflect what is actually in
the DOCX the user receives — not a partial re-derivation that omits passes. The production report and the
harness report agree on these counts for the same run.

**Why this priority:** the harness computes these on the delivered `latest_markdown` (`structural.py:90-101`);
production computes them on a partial `display_hygiene_markdown` (only 2 of the passes) and, for mixed-script,
on the RAW pre-cleanup text. So production over-reports mixed-script and can disagree with the harness on the
same run. A UI binding to production counts describes a document the user does not have.

**Independent Test:** run any book; production's `mixed_script_term_count` / `residual_bullet_glyph_count` /
`page_placeholder_heading_concat_count` / `bullet_heading_count` equal the harness's counts (both measured on the
delivered `runtime_display_markdown`).

**Acceptance Scenarios:**

1. **Given** a delivered markdown the mixed-script pass cleaned, **When** the production report is built, **Then**
   `mixed_script_term_count` reflects the CLEANED delivered text (≤ raw), not the raw count.
2. **Given** the same run, **When** the harness and production both build a report, **Then** their hygiene counts
   are equal.
3. **Given** the source-aware structural gates (false-fragment via entries, list-fragment via the entry
   resolver), **When** this change lands, **Then** they are UNCHANGED — they remain the authoritative structural
   signal (specs 001/003), not repointed at markdown.

### Edge Cases

- The reader-cleanup path builds a different `runtime_display_markdown` AFTER the report; reader-cleanup is off in
  the benchmark profile, but the report must use the `runtime_display_markdown` resolved at report-build time.
- A run where `runtime_display_markdown` is unavailable (fallback) — behaviour must degrade to today's.

## Verified findings

Verified 2026-07-11 by reading the code. Live confirmation is a success criterion (Constitution VIII).

- **Production measures a partial re-derivation, not the delivered artifact.** `_build_translation_quality_report`
  (`src/docxaicorrector/pipeline/late_phases.py:2858`) computes hygiene metrics on
  `display_hygiene_markdown = _normalize_final_markdown_for_display_hygiene_reporting(final_markdown)`
  (`:2867`), which applies ONLY `normalize_page_placeholder_heading_concats_markdown` +
  `normalize_residual_bullet_glyphs_markdown` (`:128-134`) — it omits the structural passes and mixed-script.
- **Mixed-script gated count is literally the raw count.** `mixed_script_samples = list(raw_mixed_script_samples)`
  (`late_phases.py:2892`) — the pass is never modelled, so production reports the pre-cleanup count as if it were
  the delivered count.
- **The harness already measures the delivered markdown.** `structural.py:90-101` computes
  `summarize_structure_quality_detectors`, `collect_bullet_heading_samples`,
  `collect_page_placeholder_heading_concat_samples`, `collect_residual_bullet_glyph_samples`,
  `collect_mixed_script_samples` all on `latest_markdown` = the delivered `runtime_display_markdown`
  (emitted via `emit_state(latest_markdown=runtime_display_markdown)`). So the harness is the reference for the
  correct numbers; production diverges from it.
- **The delivered markdown is available at report-build time.** `finalize_processing_success` resolves
  `runtime_display_markdown = _resolve_runtime_display_markdown(...)` (`late_phases.py:4234`) BEFORE calling
  `_build_translation_quality_report` (`:4242`). It is not currently passed in.
- **The structural gates are already source-aware and must stay so.** `false_fragment` uses
  `collect_false_fragment_heading_samples_from_entries(assembly_entries)` (`late_phases.py:2886`); `list_fragment`
  uses the entry resolver (`_resolve_list_fragment_regression_gate_samples`, spec 003). Both key on entry roles,
  not markdown, and drive the hard-fail acceptance checks (`gate_source=entry_assembly`). Repointing them at
  markdown would UNDO specs 001/003.

## Requirements *(mandatory)*

### Functional Requirements

> Binding (Constitution VII/VIII): the report describes the artifact the user receives; the authoritative
> structural signal stays source-aware. No per-book literals. Where the delivered markdown is unavailable,
> behaviour is unchanged, not guessed.

- **FR-001**: `_build_translation_quality_report` accepts the delivered `runtime_display_markdown`, threaded from
  `finalize_processing_success` (`:4242`).
- **FR-002**: The HYGIENE reporting metrics are computed on `runtime_display_markdown` instead of the partial
  `display_hygiene_markdown` / raw: `page_placeholder_heading_concat_samples`, `residual_bullet_glyph_samples`,
  `mixed_script_samples`, `bullet_heading_samples`.
- **FR-003**: `mixed_script_samples` MUST be computed on `runtime_display_markdown` (the delivered text), NOT set
  equal to `raw_mixed_script_samples`. `raw_mixed_script_samples` (on `final_markdown`) stays as the pre-cleanup
  baseline.
- **FR-004**: The source-aware STRUCTURAL gates are UNCHANGED — `false_fragment` (entries), `list_fragment`
  (entry resolver). Their `gate_source` stays `entry_assembly`. This spec does NOT repoint them at markdown.
- **FR-005**: The `raw_*` variants stay computed on `final_markdown` (the pre-display baseline).
- **FR-006**: When `runtime_display_markdown` is unavailable/empty, fall back to today's inputs so behaviour does
  not change (FR degrade-safe).

### Key Entities

- **runtime_display_markdown** — the exact string fed to `convert_markdown_to_docx_bytes`; the delivered artifact.
- **display_hygiene_markdown** — the partial re-derivation to be replaced for reporting.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: On all four books, production's `mixed_script_term_count`, `residual_bullet_glyph_count`,
  `page_placeholder_heading_concat_count`, `bullet_heading_count` equal the harness's counts for the same run.
- **SC-002**: On all four books, no acceptance verdict regresses (flips pass→fail). Expected direction: mixed-script
  gated count DROPS from raw to the cleaned-delivered count, so acceptance can only get MORE honest / not stricter
  on that axis; the hard-fail structural gates are unchanged.
- **SC-003**: `false_fragment_heading_gate_source` and `list_fragment_regression_gate_source` remain
  `entry_assembly` (specs 001/003 intact).
- **SC-004**: Full suite green; pyright ratchet ≤ 244.

## Non-goals

- **Not repointing the structural gates** at markdown — they stay entry-based (specs 001/003).
- **Not building the DOCX from entries** (increment A) — separate spec, needs per-entry role-coverage measurement.
- **Not changing thresholds, detectors' internals, or the DOCX assembly.**
- **Not adding new metrics** — only aligning existing hygiene metrics with the delivered artifact.

## Anti-regression

- **Structural gates untouched:** a test asserts `false_fragment`/`list_fragment` gate sources stay
  `entry_assembly` and the entry-based counts are unchanged by this spec.
- **Mixed-script no longer equals raw:** a test with a delivered markdown the pass cleaned asserts
  `mixed_script_term_count < raw_mixed_script_term_count` (or 0 when fully cleaned).
- **Degrade-safe:** with no `runtime_display_markdown`, the report is byte-identical to today's.
- **Harness parity:** a test (or the live 4-book check) asserts production and harness hygiene counts agree.
- **Re-baseline honestly:** the ~report tests that assert specific hygiene counts must be updated to the
  delivered-markdown values with a comment, NOT loosened. State which tests changed and why.
- **Verify on all four books by reading the produced report AND comparing to the harness verdict** (Constitution
  VIII).

## Assumptions

- `runtime_display_markdown` at `:4234` is the exact delivered text (it feeds `convert_markdown_to_docx_bytes`).
- The harness's `latest_markdown` equals that same `runtime_display_markdown` (emitted via `emit_state`), so
  matching it is the correct target.
