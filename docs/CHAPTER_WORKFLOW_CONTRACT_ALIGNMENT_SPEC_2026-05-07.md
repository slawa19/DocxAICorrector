# Chapter Workflow Contract Alignment Spec

Date: 2026-05-07
Status: Draft for approval

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
- Segment-aware job filtering and hard semantic boundaries are implemented.
- STOPPED runs already revert queued and processing segment statuses back to pending.
- Minimal failed-segment retry exists, with current-session failed-job narrowing when run log evidence is available.
- Reassembly foundations exist for `selected_only`, `selected_with_context`, `hybrid_document`, and `final_translated_book`.
- UI full-book launch already upgrades to `final_translated_book` when all required non-skipped segments are complete in the current session.
- Generic runtime events remain acceptable for the current phase; dedicated `Segment*Event` classes are optional, not mandatory.

### Confirmed gaps to address

1. `DocumentContextProfile` is under-modeled relative to the current spec contract.
2. `ProcessingContext` and `ProcessingState` are missing several segment-aware contract fields.
3. `SegmentSelection` does not exist as a first-class orchestration type.
4. Segment detection lacks explicit post-build coverage validation.
5. Oversized heading-based segments are not split into synthetic child segments.
6. Structure confirmation stores only fingerprint and settings hash, not the ordered confirmed outline snapshot.
7. Reassembly result manifest is narrower than the spec examples.
8. The API section has no dedicated internal service boundary yet; logic is still mostly embedded in UI orchestration.
9. Detection signals are missing all-caps typography use and page or section break evidence.
10. The structure settings hash is broader than necessary around `chunk_size`.
11. Segment-to-job mapping silently drops anomalous cross-boundary jobs.
12. Warnings are machine-readable keys without a dedicated user-facing normalization layer.

### Explicitly not treated as defects in this change

- Do not add dedicated `Segment*Event` classes in this slice.
- Do not add a new `ProcessingOutcome` enum value for analysis review.
- Do not treat HTTP endpoint absence alone as a bug; the first goal is internal service boundaries.
- Do not rewrite selector state just to add recommended session keys whose behavior is already derived.
- Do not treat mutable `ParagraphUnit` as a bug by itself; only address correctness risks around assignment and validation.

## Goals

1. Bring the chapter workflow implementation back into a coherent contract shape across spec, runtime, UI, and reassembly.
2. Fix the highest-signal correctness gaps first, especially contract completeness and segment validation.
3. Preserve existing working UX and processing behavior while tightening internal data contracts.
4. Introduce an internal service boundary for chapter workflow actions without requiring immediate HTTP exposure.

## Non-Goals

- No FastAPI or Flask server in this slice.
- No database-backed persistence model.
- No large UI redesign beyond modest structure review ergonomics already implied by the contract.
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

- selected-run payload builders and UI launch actions should derive from this model rather than reassembling selection state ad hoc.

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

### 10. Narrow structure settings invalidation

Refine `_build_structure_settings_hash(...)` so `chunk_size` only invalidates confirmation when it can change the effective segment structure, especially synthetic oversized-segment splitting.

### 11. Add anomaly logging in segment-to-job mapping

When a job cannot be assigned to any segment because it crosses segment boundaries:

- emit a warning log with job identity and paragraph ids;
- keep the current defensive skip rather than forcing a potentially incorrect assignment.

### 12. Normalize user-facing warnings

Keep machine-readable warning keys in detection/report structures if needed, but add a single mapping layer for UI and manifest-facing human-readable messages.

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
9. Add or update focused tests for each changed slice.

## Verification Criteria

At minimum, the implementation is acceptable when all of the following are true:

1. Preparation emits richer document-context data without regressing existing prompt generation.
2. Segment detection validates paragraph coverage and can split oversized heading-derived ranges deterministically.
3. Selected and full-book launch paths use stable selection contracts.
4. Confirmation stores enough state to validate the confirmed full outline, not only the fingerprint.
5. Reassembly result manifests expose the newly required contract fields.
6. Existing STOPPED rollback, retry behavior, and full-book gating remain intact.
7. Focused tests covering touched slices pass.

## Implementation Checklist

- [ ] Expand `DocumentContextProfile` and its builders.
- [ ] Add `SegmentSelection` model.
- [ ] Extend `ProcessingContext` and `ProcessingState`.
- [ ] Add paragraph coverage validation for detected segments.
- [ ] Add synthetic child splitting for oversized heading-based segments.
- [ ] Persist ordered confirmed segment ids alongside fingerprint and settings hash.
- [ ] Upgrade reassembly manifest contract with source token, run id, and paragraph coverage.
- [ ] Extract internal chapter workflow service boundary.
- [ ] Add all-caps typography support.
- [ ] Add page or section break evidence or explicitly mark it deferred after extraction review.
- [ ] Narrow structure settings hash invalidation around `chunk_size`.
- [ ] Add anomaly logging for cross-boundary job mapping.
- [ ] Normalize human-readable structure warnings.
- [ ] Run focused verification for touched slices.

## What Does Not Change

- No HTTP server implementation in this slice.
- No database or persistent completion model.
- No dedicated segment event family.
- No new `ProcessingOutcome` enum values.
- No broad visual redesign beyond modest structure-review adjustments required by the contract.

## Approval Request

This work changes multiple module contracts and crosses preparation, pipeline, UI, and manifest boundaries.

Per repository rules, implementation should begin only after this spec is explicitly approved.