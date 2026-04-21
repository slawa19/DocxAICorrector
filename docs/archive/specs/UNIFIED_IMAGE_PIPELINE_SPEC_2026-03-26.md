# Unified Image Pipeline Specification

**Date:** 2026-03-26
**Status:** Implemented — shared policy, delivery fidelity, and orchestration unification slices completed

## Implementation Status

- Done: centralized image-output policy layer introduced and wired into generation/restore flows.
- Done: real-document harness now records image forensic payloads from extracted assets and processed assets.
- Done: targeted regression coverage added for config wiring, policy usage, and report forensics.
- Done: size-selection and restore policy are now centralized under the image-output policy layer.
- Done: delivery fidelity for untouched payloads now reapplies preserved crop/doc metadata and source `anchor` container geometry during reinsertion.
- Done: `image_pipeline.py` now builds an explicit per-image `ImageProcessingPlan` and executes mode selection through plan-driven dispatch instead of inline branching.
- Done: plan execution is now delegated through strategy-specific helpers and a strategy registry, rather than embedding all execution branches directly inside the orchestration function.
- Done: result selection now runs through a dedicated selection-strategy dispatch layer (`skip`, `compare`, `strict_or_advisory`) instead of remaining embedded inside generation execution paths.
- Done: delivery now has an explicit model-level payload contract (`ImageDeliveryPayload`) that is synchronized on `ImageAsset` and consumed by reinsertion instead of relying only on scattered final-variant state.
- Done: orchestration now executes delivery through an explicit delivery-strategy dispatch stage and emits runtime image logs from `resolved_delivery_payload()` instead of rebuilding final outcome state ad hoc at each call site.
- Done: `no_change` passthrough now runs through the same plan-driven execution path via an explicit `none` generation strategy instead of a dedicated early-return branch.
- Done: `compare_all` now acts as a meta-mode over child image-processing plans instead of owning a separate candidate-preparation sub-pipeline, while preserving legacy incomplete-variant fallback semantics.

---

## 1. Problem

The repository currently handles image processing through several partially overlapping branches:

- `no_change`
- `safe`
- `semantic_redraw_direct`
- `semantic_redraw_structured`
- `compare_all`
- deterministic reconstruction fallback for structured diagrams/tables
- OOXML reinsertion / delivery after image selection

These branches solve related problems, but they do not share a single end-to-end contract. As a result:

1. geometry restoration logic is split across multiple functions;
2. fallback behavior is distributed between orchestration and generation layers;
3. crop / trim / output-size policy is not centralized;
4. delivery semantics differ between untouched images and AI-derived images;
5. scenario-specific bugs such as clipping can be fixed in one branch while remaining in another;
6. it is difficult to verify all scenarios uniformly.

This is now a repository-level architectural problem, not a local bug.

---

## 2. Current State

### 2.1 Scenario branching is split across two layers

`image_pipeline.py` decides high-level orchestration:

- direct passthrough for `no_change`;
- safe-only processing for `safe`;
- multi-candidate behavior for `compare_all`;
- analysis + semantic redraw attempts for semantic modes.

`image_generation.py` then performs a second layer of branching:

- safe enhancement;
- deterministic reconstruction;
- creative generate path;
- direct image-edit path;
- structured generate fallback;
- reconstruction fallback after structured failures.

This means control flow is duplicated across the orchestration layer and the candidate-generation layer.

### 2.2 Output restoration is duplicated

There are currently separate restoration helpers with overlapping responsibility:

- semantic edit preparation / restore;
- generated-image restore;
- trim helper;
- contained-output fit helper;
- preserved-output size selection;
- reconstruction render sizing.

They all try to answer versions of the same question:

"How do we map a candidate image back into the intended final geometry without clipping or distortion?"

That question should have one owner.

### 2.3 Delivery semantics are not unified

There are effectively two delivery contracts today:

- **untouched delivery** for original/safe-like outcomes;
- **AI-derived delivery** for semantic redraw / reconstructed images.

But the repository does not model these as explicit first-class delivery strategies. Instead, behavior emerges from scattered decisions in extraction, generation, and reinsertion.

### 2.4 Verification is fragmented

There is some targeted regression coverage for generated-image edge preservation, but no single matrix proving that every scenario obeys the same output contract.

---

## 3. Design Goal

Create **one unified image pipeline** with:

1. one orchestration entrypoint;
2. one scenario model;
3. one source of truth for output geometry and restoration;
4. one delivery contract for reinsertion;
5. one validation contract for candidate acceptance/rejection;
6. one scenario matrix for verification.

Scenario-specific behavior should still exist, but as **pluggable strategy steps** inside a common pipeline rather than as separate quasi-independent sub-pipelines.

---

## 4. Proposed Architecture

### 4.1 Introduce an explicit pipeline contract

Each image should move through the same stages regardless of mode:

1. **Extract**
2. **Analyze**
3. **Plan**
4. **Generate candidate(s)**
5. **Restore geometry**
6. **Validate / score**
7. **Select final delivery**
8. **Reinsert**

The current code already contains pieces of all of these stages, but they are not represented as a single contract.

### 4.2 Introduce a single `ImageProcessingPlan`

After analysis, the pipeline should build a normalized plan object, for example:

```python
ImageProcessingPlan(
    requested_mode=...,                # no_change / safe / semantic_redraw_direct / structured / compare_all
    delivery_mode=...,                 # original_passthrough / safe_raster / ai_raster
    generation_strategy=...,           # none / safe_enhance / direct_edit / vision_generate / deterministic_reconstruction
    geometry_strategy=...,             # preserve_source / restore_contained / restore_scene_graph / preserve_word_geometry
    validation_strategy=...,           # skip / advisory / strict / compare_all
    fallback_chain=[...],
)
```

This plan becomes the single source of truth for downstream behavior.

### 4.3 Separate orchestration from strategy execution

The unified orchestrator should not contain mode-specific business logic beyond selecting the plan.

Instead, strategy execution should be delegated to small components or helpers:

- `analysis_strategy`
- `candidate_strategy`
- `geometry_strategy`
- `validation_strategy`
- `delivery_strategy`

The orchestrator becomes predictable and linear; branches move into strategy tables.

### 4.4 One geometry authority

All candidate restoration should be centralized behind a single geometry service/helper, for example `image_geometry.py` or an equivalent module-level abstraction.

That authority owns:

- trim policy;
- preserved output size policy;
- contain / fit / pad decisions;
- semantic edit square-canvas preparation and restoration;
- generated-image restoration;
- deterministic reconstruction canvas normalization;
- future crop metadata application where relevant.

Rule: no image path may implement its own bespoke final-size / restore behavior outside this authority.

### 4.5 One delivery authority

Reinsertion should be driven by an explicit delivery object, for example:

```python
ImageDeliveryPayload(
    image_bytes=...,
    mime_type=...,
    delivery_kind=...,                 # original_drawing / raster_with_geometry
    source_geometry=...,
    output_geometry=...,
)
```

This makes the difference between:

- preserve original Word drawing semantics;
- deliver a new raster with intended geometry;

explicit rather than implicit.

### 4.6 `compare_all` becomes a meta-mode, not a separate pipeline

`compare_all` should not own its own partial version of the pipeline.

Instead it should:

1. construct multiple `ImageProcessingPlan` variants using the same scenario machinery;
2. run them through the same candidate / restore / validate path;
3. compare scored results;
4. emit one final delivery payload.

That removes duplicated safe/semantic preparation logic.

---

## 5. Scenario Matrix

All scenarios should be modeled inside the same matrix.

| Requested mode | Generation strategy | Geometry strategy | Validation strategy | Delivery strategy |
|---|---|---|---|---|
| `no_change` | none | preserve source | skip | original drawing / source geometry |
| `safe` | safe enhance | preserve or normalized source | skip or minimal | raster with preserved geometry |
| `semantic_redraw_direct` | direct edit, then fallback chain | unified restore | advisory/strict | raster with output geometry |
| `semantic_redraw_structured` | deterministic reconstruction or structured generate chain | unified restore / scene-graph normalize | advisory/strict | raster with output geometry |
| `compare_all` | meta-mode over the above | same as child plans | compare + score | best selected payload |

This table should drive implementation, not merely describe it.

---

## 6. What Must Be Unified

### 6.1 Candidate generation

Unify these responsibilities:

- budget handling;
- fallback chain selection;
- candidate metadata;
- revised prompt / model response metadata;
- source-to-candidate traceability.

### 6.2 Geometry restoration

Unify these responsibilities:

- trim detection;
- padding restoration;
- target-size selection;
- containment vs non-lossy restore;
- reconstruction overflow guardrails;
- future crop support.

### 6.3 Validation and selection

Unify these responsibilities:

- validation result shape;
- advisory vs strict policy;
- soft accept / hard reject semantics;
- scoring rules;
- fallback-to-safe / fallback-to-original decisions.

### 6.4 Reinsertion and final delivery

Status update: implemented. Untouched delivery now reapplies preserved `a:srcRect`, source `docPr` metadata, and source `anchor` container geometry during reinsertion; explicit delivery objects are synchronized on `ImageAsset`; runtime orchestration/logging consume the resolved delivery payload; and `compare_all` executes child modes through the shared plan-driven pipeline instead of a bespoke compare-only branch.

Unify these responsibilities:

- untouched source delivery;
- AI-derived raster delivery;
- source geometry preservation;
- future OOXML crop / drawing semantics support.

---

## 7. Refactoring Plan

### Phase 1: Scenario inventory and forensic matrix

Document and test all scenarios:

- `no_change`
- `safe`
- `semantic_redraw_direct`
- `semantic_redraw_structured`
- `compare_all`
- reconstruction fallback
- generate fallback
- safe fallback

Add a scenario matrix test harness so every future fix is evaluated across all paths.

### Phase 2: Introduce normalized planning objects

Create explicit plan / candidate / delivery abstractions.

The existing code can initially adapt to them without immediate logic changes.

### Phase 3: Centralize geometry restoration

Move all trim / restore / output-size logic behind one geometry authority.

This phase also becomes the main place to fix clipping issues across structured and creative redraw.

### Phase 4: Unify orchestration and fallback chains

Refactor `image_pipeline.py` and `image_generation.py` so mode selection builds plans, and strategy execution runs those plans.

Goal: one orchestration path, multiple strategy implementations.

### Phase 5: Unify delivery and reinsertion

Make final reinsertion consume a normalized delivery payload rather than infer behavior from loosely coupled fields.

### Phase 6: Externalize image policy config

Move shared image policy into config-driven structures:

- trim thresholds;
- padding ratios;
- API size candidates;
- geometry margins;
- reconstruction overflow guards;
- delivery policy toggles.

---

## 8. One Source of Truth

After refactor, the repository should have one source of truth in each category:

- **scenario truth**: `ImageProcessingPlan`
- **geometry truth**: unified geometry authority
- **selection truth**: unified validation/selection rules
- **delivery truth**: normalized delivery payload
- **policy truth**: config-backed image policy

If a future feature needs image-specific behavior, it must plug into one of those five authorities rather than create a parallel path.

---

## 9. Verification Criteria

1. Every image mode is covered by scenario-matrix tests.
2. The same clipping regression can be tested against structured redraw, direct redraw, generate fallback, and compare-all.
3. No final-size / restore logic remains duplicated in multiple branches.
4. `compare_all` uses the same child-plan pipeline rather than bespoke preparation logic.
5. `no_change` preserves source delivery semantics through the normalized delivery contract.
6. Configuration changes affect all relevant branches through one policy layer.

---

## 10. What Does Not Change

- the user-facing image modes can remain the same;
- the existing model choices can remain the same initially;
- real-document validation remains the top-level regression harness;
- the crop-fidelity spec remains relevant as a focused sub-problem under this broader architecture.

---

## 11. Relationship To Existing Spec

`IMAGE_SIZING_REFACTORING_SPEC_2026-03-26.md` remains the focused investigation for clipping / fidelity defects.

This specification supersedes it only at the architectural level:

- the sizing/crop spec explains **what is broken** in specific branches;
- this unification spec explains **how the whole image system should be reorganized** so those fixes are implemented once and reused everywhere.

## 12. Completion Note

Post-implementation verification confirms that the specification is materially closed in the current codebase:

- scenario-matrix coverage exists in the integration suite for `no_change`, `safe`, `semantic_redraw_direct`, `semantic_redraw_structured`, and `compare_all`;
- source drawing forensics and `a:srcRect` round-tripping are covered in document extraction/reinsertion tests;
- delivery now flows through explicit `ImageDeliveryPayload` resolution in orchestration and reinsertion;
- `compare_all` executes child modes through shared plan machinery while preserving legacy incomplete-variant fallback behavior;
- centralized image-output policy wiring is present in generation/restore flows.