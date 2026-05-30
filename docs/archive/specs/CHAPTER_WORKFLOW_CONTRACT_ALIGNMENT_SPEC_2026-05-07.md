# Chapter Workflow Contract Alignment Spec

Date: 2026-05-07
Status: Archived 2026-05-30; dead-end / superseded by reader-first migration

## Problem

The current implementation of the chapter-based workflow is functionally ahead of the original MVP, but several contracts now diverge across:

- the chapter workflow spec;
- the in-memory processing contracts;
- the structure review UI state model;
- the reassembly manifest shape;
- the document-context prompt model.

Two review passes identified a mixed set of valid gaps, overstatements, and already-implemented items. Before changing code, the repo needs one approved alignment plan that distinguishes:

- real contract gaps that should be implemented now;
- items that are already satisfied and must not be reworked unnecessarily;
- items that should be treated as deferred or spec cleanup rather than code defects.

## Current State

### Already working and not to be regressed

- Segment detection, segment diagnostics, structure fingerprinting, and manifest export are implemented.
- Guardrails already prevent silent segment-scoped execution when coverage is invalid, mapping is incomplete, or the outline is not confirmed.
- Segment-aware job filtering and hard semantic boundaries are implemented.
- Segment coverage validation and stale cross-boundary mapping blocking are implemented.
- STOPPED runs already revert queued and processing segment statuses back to pending.
- Minimal failed-segment retry exists, with current-session failed-job narrowing when run log evidence is available.
- Persisted failed-job reuse for the same prepared identity now exists and is preferred after current-session run-log evidence.
- Reassembly foundations exist for `selected_only`, `selected_with_context`, `hybrid_document`, and `final_translated_book`.
- Reassembly manifests already include `source_token`, `run_id`, `coverage.segment_ids`, and `coverage.paragraph_ranges`.
- `ProcessingContext` and `ProcessingState` already carry the current segment-aware fields used by the pipeline.
- `DocumentContextProfile` is already expanded, and `detected_author` now populates from DOCX core properties when source metadata is available.
- UI full-book launch already upgrades to `final_translated_book` when all required non-skipped segments are complete in the current session.
- Structure confirmation already persists `confirmed_segment_ids` alongside the confirmed fingerprint and settings hash.
- Deterministic `segment_id`, `boundary_fingerprint`, and `structure_fingerprint` behavior is protected by direct regression tests.
- Generic runtime events remain acceptable for the current phase; dedicated `Segment*Event` classes are optional, not mandatory.

### Confirmed gaps to address

1. `SegmentSelection` now drives selected/retry orchestration, survives into pipeline context, and is persisted into selected-run result manifests, but block execution and most downstream processing logic still act on normalized `selected_segment_ids` rather than the richer selection object.
2. Prompt enrichment now includes current block-specific segment framing during translated block execution and current-run previous completed segment summary, but it still does not persist continuity state across runs.
3. `detected_author` is still limited by the source contract: DOCX core properties are supported, but non-DOCX author metadata is not reliably available.
4. Page or section break evidence remains deferred because the current extraction contract does not expose that metadata.
5. The primary structure-review surface still exposes technical detector details and raw noisy titles instead of clearly answering which parts of the document will enter partial translation.

### Explicitly not treated as defects in this change

- Do not add dedicated `Segment*Event` classes in this slice.
- Do not add a new `ProcessingOutcome` enum value for analysis review.
- Do not treat HTTP endpoint absence alone as a bug; the first goal is internal service boundaries.
- Do not rewrite selector state just to add recommended session keys whose behavior is already derived.
- Do not treat mutable `ParagraphUnit` as a bug by itself; only address correctness risks around assignment and validation.

## Goals

1. Bring the chapter workflow implementation back into a coherent contract shape across spec, runtime, UI, and reassembly.
2. Keep the spec focused on real remaining gaps rather than already-landed implementation.
3. Redesign the structure-review surface so it is understandable to a normal user reviewing partial translation scope.
4. Continue moving selection/retry orchestration toward stable service-layer contracts without requiring immediate HTTP exposure.

## Non-Goals

- No FastAPI or Flask server in this slice.
- No database-backed persistence model.
- No new backend workflow or detector family just to support the UI redesign.
- No new nested chapter tree UI model.
- No dedicated event-family redesign.

## Proposed Changes

### 1. Expand `DocumentContextProfile`

Bring `DocumentContextProfile` closer to the current spec contract.

Required fields:

- `source_token`
- `structure_fingerprint`
- `source_title`
- `detected_author`
- `source_language`
- `target_language`
- `translation_domain`
- `style_instructions`
- `glossary_terms`
- `segment_outline`

Implementation rule:

- keep prompt generation backward-compatible;
- continue rendering outline and glossary when richer fields are unavailable;
- populate the fields that are already knowable during preparation now, and use stable empty defaults only where the source data truly does not exist yet.

### 2. Align processing contracts

Extend `ProcessingContext` with:

- `document_segments`
- `segment_selection_mode`

Extend `ProcessingState` with:

- `segment_outputs`
- `completed_segment_ids`
- `failed_segment_ids`

Implementation rule:

- existing session-state based UI status tracking stays in place;
- these fields become the pipeline-facing structured state contract rather than replacing the UI state model immediately.

### 3. Introduce `SegmentSelection`

Add a first-class `SegmentSelection` model that captures:

- selected segment ids;
- descendant inclusion policy;
- front matter inclusion;
- TOC inclusion;
- output mode.

Implementation rule:

- selected-run payload builders and UI launch actions should derive from this model rather than reassembling selection state ad hoc;
- downstream execution may continue consuming normalized `selected_segment_ids` until a later contract pass needs the richer object end-to-end, but pipeline context and selected-run manifests should preserve the richer selection metadata when it is available.

### 4. Add segment coverage validation

After segment construction, validate that:

- every paragraph index in the prepared paragraph list is covered;
- no paragraph index is covered more than once;
- every segment range is internally consistent.

Failure policy:

- emit segment-detection warnings when recoverable;
- raise or hard-fail only if the segmentation result is structurally impossible for downstream processing.

### 5. Split oversized heading-based segments

Implement synthetic child-segment splitting for oversized heading-derived segments when processing limits require it.

Rules:

- preserve the original parent segment as the conceptual boundary owner;
- generate deterministic synthetic child ids and titles;
- only split when the segment exceeds the configured safe processing threshold;
- keep fallback splitting logic and heading-based splitting behavior aligned.

### 6. Strengthen structure confirmation snapshot

Persist an ordered full-outline snapshot at confirmation time, including confirmed segment ids.

Rules:

- confirmation continues to be tied to the full outline, not the current filtered subset;
- confirmation invalidation should compare against the current detected outline and current settings hash;
- keep the current fingerprint-based UX, but add the underlying ordered snapshot needed for strict contract validation.

### 7. Upgrade reassembly manifest contract

Extend the result manifest with:

- `source_token`
- `run_id`
- `coverage.segment_ids`
- `coverage.paragraph_ranges`

Implementation rule:

- keep existing fields for backward compatibility where practical;
- compute paragraph ranges from included source paragraphs instead of guessing from selected ids alone.

### 8. Add chapter workflow service boundary

Introduce an internal service module for chapter-workflow actions such as:

- analyze result projection;
- structure confirmation;
- structure manifest export;
- selected run request building;
- retry request building;
- full-book launch request building;
- reassembly request building.

This does not expose HTTP yet. It only establishes stable internal contracts that match the API section closely enough to make later HTTP exposure straightforward.

### 9. Tighten detection signals

Update segment detection to:

- use all-caps as part of typography evidence when available;
- include page or section break evidence when the extracted paragraph model exposes usable signals;
- keep these as supporting evidence rather than standalone hard boundaries.

If raw extraction does not yet expose page or section break metadata, this slice should:

- add the paragraph fields if extraction can provide them cheaply; or
- explicitly mark that evidence path as deferred in the chapter workflow spec after confirming extraction limitations.

Extraction review 2026-05-07:

- current `ParagraphUnit` and the active extraction path do not expose `page_break`, `section_break`, or equivalent paragraph-boundary metadata;
- page or section break evidence is therefore deferred until the extraction contract grows those fields.

### 10. Narrow structure settings invalidation

Refine `_build_structure_settings_hash(...)` so `chunk_size` only invalidates confirmation when it can change the effective segment structure, especially synthetic oversized-segment splitting.

### 11. Add anomaly logging in segment-to-job mapping

When a job cannot be assigned to any segment because it crosses segment boundaries:

- emit a warning log with job identity and paragraph ids;
- keep the current defensive skip rather than forcing a potentially incorrect assignment.

### 12. Normalize user-facing warnings

Keep machine-readable warning keys in detection/report structures if needed, but add a single mapping layer for UI and manifest-facing human-readable messages.

Rules:

- primary review messages should explain whether the outline is ready, what will be translated, and what must be reviewed first;
- job-level and fingerprint-level diagnostics should not appear inline in the main review list;
- when mapping is incomplete, explain the remediation in document terms (`re-prepare the document`) rather than pipeline terms.

### 13. Redesign the structure review surface

Reframe the chapter selector as a section-review surface.

Rules:

- the main surface must answer `what will be translated if I run a partial translation now?`;
- section titles shown to the user must be sanitized to remove image placeholders, markdown markup, and other extraction noise where possible;
- inline labels should prefer user-facing concepts such as section type, hierarchy, word count, confidence, and current run status;
- raw boundary fingerprints, detector versions, and manifest comparison tools must move behind an advanced/debug affordance instead of appearing inline in the main review path;
- boundary inspection should use a plain-language included-text preview (`starts with`, `ends with`) rather than raw boundary diagnostics;
- image placeholders inside a title must not cause the UI to present a section as if it were an image block.

## Module Boundaries And Dependency Direction

### Document / preparation layer

Affected modules:

- `src/docxaicorrector/document/segments.py`
- `src/docxaicorrector/core/models.py`
- `src/docxaicorrector/processing/preparation.py`
- `src/docxaicorrector/ui/application_flow.py`

Responsibilities:

- expand segment and document-context models;
- validate segment coverage;
- create synthetic child segments when required;
- pass richer segment and prompt context through prepared data.

### Pipeline contract layer

Affected modules:

- `src/docxaicorrector/pipeline/contracts.py`
- `src/docxaicorrector/pipeline/setup.py`
- `src/docxaicorrector/pipeline/_pipeline.py`
- `src/docxaicorrector/pipeline/late_phases.py`

Responsibilities:

- thread expanded processing contracts through runtime;
- populate structured segment state fields;
- carry richer manifest inputs.

### Reassembly layer

Affected modules:

- `src/docxaicorrector/pipeline/reassembly.py`
- `src/docxaicorrector/runtime/artifacts.py`

Responsibilities:

- extend reassembly result manifest shape;
- compute segment coverage metadata.

### UI / orchestration layer

Affected modules:

- `src/docxaicorrector/ui/structure_review_panel.py`
- `src/docxaicorrector/ui/_app.py`
- `src/docxaicorrector/runtime/state.py`

Responsibilities:

- store full confirmation snapshot;
- consume normalized warning messages;
- present a user-first section review surface while keeping advanced diagnostics available on demand;
- build launches via the new service boundary rather than ad hoc payload assembly.

### Service boundary layer

New module group, localized and small:

- `src/docxaicorrector/chapter_workflow/` or equivalent low-risk location under existing source layout.

Responsibilities:

- define internal request and response builders aligned with the API section;
- keep UI thin without introducing HTTP yet.

## Consumer Update Plan

1. Expand data models and keep defaults backward-compatible.
2. Add segment coverage validation and oversized child splitting.
3. Add `SegmentSelection` and thread it through selected-run orchestration.
4. Extend processing contracts and segment-aware state.
5. Add structure confirmation snapshot storage.
6. Upgrade reassembly manifest fields.
7. Extract internal chapter workflow service boundary.
8. Tighten detection evidence, settings invalidation, and anomaly logging.
9. Redesign the review surface to hide internals behind advanced tools and sanitize titles/previews.
10. Add or update focused tests for each changed slice.

## Verification Criteria

At minimum, the implementation is acceptable when all of the following are true:

1. Preparation emits richer document-context data without regressing existing prompt generation.
2. Segment detection validates paragraph coverage and can split oversized heading-derived ranges deterministically.
3. Selected and full-book launch paths use stable selection contracts.
4. Confirmation stores enough state to validate the confirmed full outline, not only the fingerprint.
5. Reassembly result manifests expose the newly required contract fields.
6. Existing STOPPED rollback, retry behavior, and full-book gating remain intact.
7. The primary review surface tells the user what will be translated without exposing raw internal detector identifiers inline.
8. Focused tests covering touched slices pass.

## Implementation Checklist

- [x] Expand `DocumentContextProfile` and its builders.
- [x] Add `SegmentSelection` model.
- [x] Thread `SegmentSelection` through selected/retry UI-service launch orchestration.
- [x] Extend `ProcessingContext` and `ProcessingState`.
- [x] Add paragraph coverage validation for detected segments.
- [x] Add synthetic child splitting for oversized heading-based segments.
- [x] Persist ordered confirmed segment ids alongside fingerprint and settings hash.
- [x] Upgrade reassembly manifest contract with source token, run id, and paragraph coverage.
- [x] Extract internal chapter workflow service boundary.
- [x] Add all-caps typography support.
- [x] Add page or section break evidence or explicitly mark it deferred after extraction review.
- [x] Narrow structure settings hash invalidation around `chunk_size`.
- [x] Add anomaly logging for cross-boundary job mapping.
- [x] Normalize human-readable structure warnings.
- [x] Run focused verification for touched slices.

## What Does Not Change

- No HTTP server implementation in this slice.
- No database or persistent completion model.
- No dedicated segment event family.
- No new `ProcessingOutcome` enum values.
- No broad visual redesign beyond modest structure-review adjustments required by the contract.

## Approval Request

This work changes multiple module contracts and crosses preparation, pipeline, UI, and manifest boundaries.

Per repository rules, implementation should begin only after this spec is explicitly approved.