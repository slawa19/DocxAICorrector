# Registry-Aware Final Paragraph Assembly Spec

## Problem

The current final-markdown cleanup in `src/docxaicorrector/pipeline/output_validation.py` uses text-local heuristics to repair false fragment headings and inline paragraph splits after model output. This improves some regressions, but it cannot reliably satisfy both of these constraints at once:

1. preserve legitimate structural boundaries such as TOC sections, year labels, and real headings;
2. rejoin PDF-derived fragment paragraphs that should become continuous prose.

Recent canonical reruns of `end-times-pdf-core` show the ceiling of the current approach:

- if merge heuristics are permissive, the pipeline reopens `toc_body_concatenation_detected` and large paragraph-count drift;
- if merge heuristics are conservative, the pipeline reopens `false_fragment_headings_present` and `key_headings_preserved` failures;
- both failure modes occur despite `enable_paragraph_markers=true` at generation time and an existing `generated_paragraph_registry` being available in the pipeline state.

## Current State

The relevant flow today is:

1. semantic-block building adds paragraph markers and stores `target_text_with_markers`, `paragraph_ids`, and structural hints in the job payload;
2. generation validates the marker contract and strips the literal markers before returning the cleaned `processed_chunk`;
3. block execution builds `generated_paragraph_registry` from the cleaned `processed_chunk`, keyed by `paragraph_id`;
4. late phases assemble `current_markdown_fn(state.processed_chunks)` into one markdown string;
5. final cleanup mutates that raw markdown string with regex-based normalizers;
6. DOCX restoration receives the registry for paragraph-property restoration, but quality validation and final markdown artifacts are based on the postprocessed string, not a registry-aware boundary model.

This means the system already has a durable paragraph-identity carrier after generation, but it is `generated_paragraph_registry`, not the literal markers. The final cleanup ignores that registry and instead guesses paragraph intent from neighboring strings.

## Proposed Change

Introduce a registry-aware final paragraph assembly and boundary-recovery layer that operates on paragraph entries before final markdown serialization.

### Core design

1. Add a final-assembly helper that accepts `processed_chunks`, `generated_paragraph_registry`, and `source_paragraphs`, and returns normalized ordered paragraph entries plus final markdown.
2. Enrich generated registry entries by joining them with `source_paragraphs` via `paragraph_id` before any recovery logic runs.
3. Move false-heading and inline-fragment recovery from raw-string heuristics to registry-aware neighbor operations.
4. Allow merges only when they produce an explicit recovery decision between adjacent enriched paragraph entries.
5. Preserve structural boundaries when either side is known or inferred as:
   - TOC header or TOC entry;
   - markdown heading / title-like section heading;
   - numbered or phased section label such as `Год 5` or `3/3.)`;
   - blockquote paragraph.
6. Rebuild final markdown from the recovered paragraph list, then apply only paragraph-local normalizers such as mixed-script cleanup or residual bullet glyph normalization.

### Assembly invariants

The assembly helper must preserve these invariants:

1. Recovery may merge adjacent paragraph entries, but must not reorder entries, duplicate entries, or join non-adjacent entries.
2. Recovery must be monotonic with respect to protected structural boundaries: if either side is classified as a protected boundary, merge is denied unless a narrow allow-rule explicitly names that boundary combination.
3. Registry coverage may be partial because passthrough blocks and non-marker execution paths can still contribute to `processed_chunks` without adding `generated_paragraph_registry` entries. The first implementation must fail open for uncovered spans by preserving the original `processed_chunks` text for those spans, not by dropping content or inventing paragraph ids.
4. If registry ordering or counts are inconsistent with `processed_chunks`, the helper must log diagnostics and fall back to the existing string assembly path for the affected span.
5. The same helper must be used by image processing, DOCX build, and final success paths so `latest_markdown`, DOCX input markdown, quality validation, and saved UI artifacts are based on the same deterministic assembly logic.

### First vertical slice

The first implementation slice should stay in the late-assembly layer rather than changing marker generation or block execution contracts.

1. Keep the existing marker validation and registry construction path unchanged.
2. Add one internal helper for registry-aware final paragraph assembly.
3. Replace the repeated late-phase string cleanup chains with that single helper.
4. Leave generation-time marker rules and block-level contracts intact unless the new assembly path proves they are insufficient.

### Data model direction

Add a small internal paragraph-boundary representation containing at least:

- `paragraph_id`
- `block_index`
- `text`
- `source_index`
- `role`
- `structural_role`
- `heading_level`
- `list_kind`
- `boundary_source`
- `boundary_confidence`
- `kind` or inferred boundary flags for heading / quote / toc / list / body / section-label
- optional merge provenance for diagnostics

These fields should come from `source_paragraphs` wherever possible rather than being re-inferred from generated text alone.

### Quality and diagnostics

1. Emit boundary-recovery diagnostics alongside existing formatting diagnostics.
2. Record merge decisions with source paragraph ids so real-document failures can be inspected deterministically.
3. Update document-level quality validation to consume the recovered paragraph ordering rather than only the final raw markdown string when possible.
4. Include fallback diagnostics for uncovered or inconsistent registry spans so partial-registry behavior is visible in real-document runs.
5. Include counters for accepted merges, denied merges, protected-boundary denials, registry-covered paragraphs, fallback paragraphs, and final paragraph count drift versus the original assembled markdown.

## Consumer Update Plan

Affected modules likely include:

- `src/docxaicorrector/pipeline/late_phases.py`
- `src/docxaicorrector/pipeline/output_validation.py`
- `src/docxaicorrector/pipeline/contracts.py`
- `src/docxaicorrector/validation/structural.py`
- `src/docxaicorrector/core/models.py` as the metadata source consumed by enrichment logic
- possibly `src/docxaicorrector/generation/formatting_transfer.py` if diagnostics need boundary metadata

The preferred rollout is:

1. introduce an enrichment-and-assembly helper and tests without changing public output contracts;
2. route final markdown assembly through the registry-aware path in late phases;
3. extend validation/diagnostics to expose recovery decisions;
4. rerun canonical real-document profiles and tighten tests around `end-times-pdf-core`.

The first slice should avoid changing `BlockExecutionPayload`, marker validation, or DOCX restoration public signatures unless tests prove the existing registry shape cannot support safe enrichment. If additional metadata is needed, prefer deriving it from `source_paragraphs` by `paragraph_id` inside the assembly helper before widening pipeline contracts.

## What Does Not Change

- the WSL-first runtime and canonical validation paths;
- OpenAI block generation contract and paragraph marker validation contract;
- the fact that literal paragraph markers are stripped during generation and do not survive into late-phase final markdown assembly;
- DOCX formatting restoration entrypoints;
- current image pipeline behavior.

## Verification Criteria

The change is complete when all of the following are true:

1. `tests/test_document_pipeline_output_validation.py` stays green.
2. New focused assembly/recovery tests cover TOC-backed headings, blockquote continuations, section labels, and PDF fragment merges.
3. Canonical rerun of `end-times-pdf-core` no longer fails on `false_fragment_headings_present` or `toc_body_concatenation_detected`.
4. Formatting diagnostics for the same run show materially reduced unmapped source/target counts.
5. `key_headings_preserved` passes for the real-document harness.
6. A partial-registry test proves passthrough or uncovered spans are preserved exactly rather than dropped or reordered.
7. A consistency test proves image processing, DOCX build, quality validation, and saved UI artifacts receive identical final markdown for the same state.

## Follow-up Work After Heading Recovery

### Current canonical status (2026-05-03)

The registry-aware heading recovery slice is considered implemented and canonically validated for `end-times-pdf-core` when the latest completed real-document run shows all of the following at the same time:

- `false_fragment_heading_count == 0` and `false_fragment_heading_samples == []`;
- `toc_body_concat_detected == false`;
- the acceptance check `key_headings_preserved` passes;
- `boundary_recovery.fallback_paragraphs == 0`;
- `boundary_recovery.inconsistent_registry_blocks == []`;
- `boundary_recovery.registry_covered_paragraphs` covers the prepared paragraph count for the profile.

The follow-up work below must not reopen heading recovery. Treat any recurrence of `false_fragment_headings_present`, `toc_body_concatenation_detected`, or `key_headings_preserved` failure as a regression in the completed heading slice and fix it before continuing lower-priority cleanup.

### Remaining strict quality-gate failures

After heading recovery, the remaining `end-times-pdf-core` failures are expected to be in these categories:

1. `mixed_script_terms_present` — paragraph-local Cyrillic/Latin homoglyph residue.
2. `residual_bullet_glyphs_present` — literal bullet glyphs such as `●` that survived in prose or list text.
3. `list_fragment_regressions_present` — dangling ordered-list markers such as `intro: 1.`, `body 2.`, or marker-only emoji/number fragments.
4. `unmapped_source_paragraphs_present` — formatting restoration coverage still reports unmapped source/target paragraphs after accepted paragraph merges.

These are intentionally separate from heading recovery. Fix them in small, independently verifiable layers rather than adding broad recovery rules to the heading classifier.

### Follow-up layer 1: paragraph-local final normalization

Goal: make canonical final markdown, DOCX input markdown, quality validation, and saved UI artifacts receive the same safe paragraph-local cleanup that runtime display previously applied opportunistically.

Scope:

- Apply mixed-script homoglyph repair to final assembly output, including registry-backed entries.
- Apply residual bullet glyph cleanup to body/list paragraphs, including registry-backed entries.
- Keep these operations paragraph-local: no reordering, no cross-paragraph merges, and no heading/body boundary changes.
- Do not change `generated_paragraph_registry`, marker validation, block execution contracts, or DOCX restoration public signatures.

Important implementation constraint:

- The registry-aware path currently preserves registry-backed entry text verbatim. Follow-up normalization should be introduced as an explicit final-entry/post-assembly normalization step so that canonical artifacts do not differ from runtime display.

Suggested focused tests:

- mixed-script repair applies to registry-backed entries (`чашa` -> `чаша`) without altering legitimate Latin terms such as `OpenAI`, `BMW`, or glossary terms intentionally written in Latin;
- inline `●` inside body prose is removed or converted to spacing without joining unrelated text;
- inline `●` inside existing Markdown list items is removed from item content;
- leading `● text` is converted to `- text` only for body/list paragraphs, not for headings or blockquotes;
- image phase, DOCX build, final runtime state, quality report, and UI artifacts still use one canonical final markdown string.

Completion criteria for layer 1:

- focused output-validation and pipeline quality-report tests pass;
- canonical `end-times-pdf-core` rerun keeps the heading-slice invariants passing;
- `mixed_script_term_count == 0`;
- `residual_bullet_glyph_count == 0` or is reduced to only documented false positives with samples added to this spec before acceptance;
- gate reasons no longer include `mixed_script_terms_present` or `residual_bullet_glyphs_present` unless an explicit false-positive decision is documented.

### Follow-up layer 2: list-fragment recovery

Goal: repair deterministic ordered-list marker fragments that remain after paragraph-local glyph cleanup.

Scope:

- Handle intro lines ending in a dangling first marker, for example `...: 1.`.
- Handle short body fragments ending in the next ordered marker, for example `... 2.` or `... 3.` when neighboring entries prove an ordered-list sequence.
- Preserve real prose containing numbers, verse references, years, section labels, and emoji that are not proven list markers.
- Prefer entry-aware/neighbor-aware recovery over flat-string cleanup when `FinalAssemblyEntry` data is available.

Suggested focused tests:

- `intro: 1.` followed by a body/list continuation becomes `intro:` plus `1. continuation`;
- sequential `body 2.` / `body 3.` fragments are restored to ordered list items only when adjacent context supports the sequence;
- scripture references and year labels are not rewritten as list markers;
- emoji-plus-number fragments are either safely repaired or explicitly excluded with a documented sample and reason.

Completion criteria for layer 2:

- focused list-fragment tests pass;
- canonical `end-times-pdf-core` rerun keeps the heading and paragraph-local cleanup invariants passing;
- `list_fragment_regression_count == 0` or remaining samples are documented as accepted false positives;
- gate reasons no longer include `list_fragment_regressions_present` unless an explicit false-positive decision is documented.

### Follow-up layer 3: formatting diagnostics and unmapped paragraphs

Goal: reduce `unmapped_source_paragraphs_present` only after heading, mixed-script, bullet-glyph, and list-fragment output is stable.

Do not start this layer until prior layers are stable, because every boundary merge, bullet cleanup, or list repair can change formatting restoration coverage.

Investigation checklist:

- inspect the latest `.run/formatting_diagnostics/restore_*.json` referenced by `translation_quality_report.formatting_diagnostics_artifact_paths`;
- compare `source_paragraph_count`, `target_paragraph_count`, `mapped_count`, `unmapped_source_count`, `unmapped_target_count`, `accepted_merged_sources_count`, and `boundary_recovery.paragraph_count_drift`;
- classify unmapped sources into accepted merge coverage, true text loss, list/heading boundary shifts, and mapping-policy limitations;
- prefer improving restoration diagnostics/mapping policy over weakening the quality gate.

Completion criteria for layer 3:

- canonical `end-times-pdf-core` rerun keeps all previous layers passing;
- formatting diagnostics show materially reduced unmapped source/target counts compared with the heading-recovery baseline;
- `unmapped_source_paragraphs_present` is removed from strict gate reasons, or the remaining unmapped sources are explicitly classified as accepted/benign by deterministic diagnostics;
- no DOCX restoration regression is introduced for captions, headings, lists, or image placeholders.

### Overall completion criteria

The full paragraph-boundary recovery effort is complete when a canonical `end-times-pdf-core` rerun under `ui-parity-pdf-structural-recovery` completes through DOCX build and quality validation with:

- no early block-level rejection such as `english_residual_output`;
- heading-slice invariants still passing;
- `mixed_script_term_count == 0`;
- `residual_bullet_glyph_count == 0`;
- `list_fragment_regression_count == 0`;
- `unmapped_source_paragraphs_present` absent from strict gate reasons, or remaining unmapped sources deterministically classified as accepted/benign;
- `quality_status == "pass"` for strict translation quality gate, except for explicitly documented advisory-only theology style findings;
- all focused unit tests for output validation, quality report routing, partial registry preservation, and final-markdown consistency passing through the canonical WSL test entrypoint.

## Why This Is The Right Architecture

The repository already pays the cost to preserve paragraph identity through a generation-time marker contract and a durable `generated_paragraph_registry`. Re-solving paragraph-boundary errors from the flattened markdown string throws away that structure and forces fragile regex guesses. The durable fix is to use the registry plus source paragraph metadata during final assembly and make merge/split decisions explicitly at that layer.
