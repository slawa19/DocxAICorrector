# Structure Recognition Input Fidelity Spec

Date: 2026-05-21
Status: Archived 2026-05-30; dead-end / superseded by reader-first migration
Parent specs:

- `docs/AI_FIRST_STRUCTURE_RECOVERY_SPEC_2026-05-08.md`
- `docs/specs/TOPOLOGY_FIRST_STRUCTURE_RECOVERY_REMEDIATION_SPEC_2026-05-12.md`
- `docs/specs/LAYOUT_SIGNAL_EVIDENCE_SLICE_SPEC_2026-05-14.md`
- Companion output spec:
  `docs/specs/OUTPUT_DISPLAY_HYGIENE_AND_STRUCTURE_DETECTORS_SPEC_2026-05-21.md`

## Summary

Improve Stage 1 / Stage 2 structural preparation by making PDF-furniture and
structural-damage signals explicit inputs to the AI-first pipeline instead of
relying on the model to infer them from truncated previews or on final Markdown
cleanup to hide them later.

This spec does not add another final Markdown structural fixer. It improves input
fidelity for the existing AI-first authority path:

```text
PDF/DOCX extraction
  -> deterministic signal extraction, no text mutation
  -> Stage 1 DocumentMap sees longer previews + explicit contamination hints
  -> Stage 1 returns outline / anchors / split_hints / review_zones
  -> Stage 1.5 topology projection consumes existing DocumentMap authority
  -> Stage 2 anchored classification keeps using DocumentMap/topology context
  -> output detectors verify final reader-visible result
```

The key rule is:

```text
If a structural defect can be made visible before Stage 1, expose it as a
bounded descriptor signal. Do not compensate for missing input fidelity by adding
broader final Markdown rewrites.
```

## Problem

The current AI-first structure pipeline already has the right architecture in
broad strokes: Stage 1 `DocumentMap` gives the model a global document view,
Stage 1.5 projects topology, and Stage 2 classifies with anchors. However, the
actual Stage 1 input is not high-fidelity enough for several PDF-derived defects.

Observed failure classes:

- blank-page markers embedded inside long paragraphs;
- page-furniture text concatenated with semantic headings;
- compound TOC entries whose split parts need explicit authority;
- heading/body concatenation candidates hidden beyond short previews;
- attribution or epigraph-like material misread as heading material;
- Stage 2 window seams that are invisible in diagnostics when adjacent heading
  fragments land near a boundary.

A stronger model can help only when the defect is present in the prompt and the
schema tells the model what responsibility it has. The current code sometimes
hides the defect before the model can reason about it.

## Verified Current State

### Stage 1 Is Global But Previewed

`build_document_map(...)` is a single Stage 1 call over sampled descriptors:

- `src/docxaicorrector/structure/document_map.py:151`
- default `preview_chars = 120` at
  `src/docxaicorrector/structure/document_map.py:159`
- descriptors use `text[:preview_limit]` at
  `src/docxaicorrector/structure/document_map.py:240`

The runtime config currently reads `structure_recovery_document_map_preview_chars`
with default `120` at `src/docxaicorrector/processing/preparation.py:798`.

The config clamp currently limits `structure_recovery_document_map_preview_chars`
to `40..400`:

- `src/docxaicorrector/core/config_structure_sections.py:624`

Therefore, `120 -> 400` is the safe first-step increase. `600+` requires a
separate clamp change.

### Stage 1 Sampling Can Still Drop Descriptors

`select_document_map_logical_indexes(...)` samples descriptors when count or
estimated token budget is exceeded:

- `src/docxaicorrector/structure/document_map.py:318`

Current structural importance is a flat boolean OR over style/layout/TOC/scripture
signals, embedded hints, short text, and explicit headings:

- `src/docxaicorrector/structure/document_map.py:1775`

The selected set is still passed through `_shrink_logical_indexes_to_token_budget`:

- `src/docxaicorrector/structure/document_map.py:328`
- `src/docxaicorrector/structure/document_map.py:344`
- `src/docxaicorrector/structure/document_map.py:354`

This matters because increasing preview length can increase prompt size and cause
previously included descriptors to be dropped under `max_input_tokens`.

### Stage 1 Already Has Split Hints

The DocumentMap prompt already requests `split_hints`:

- `src/docxaicorrector/structure/document_map.py:621`

It specifically instructs compound TOC entry handling:

- `src/docxaicorrector/structure/document_map.py:628`

The current split kinds are:

- `page_artifact_heading`
- `compound_toc_entries`

as allowed in `src/docxaicorrector/structure/document_map.py:59`.

Therefore this spec is not adding the split-hint concept from scratch. It makes
PDF-furniture contamination an explicit Stage 1 responsibility and ensures the
model receives enough signal to use the existing mechanism.

### Topology Already Has Candidate Page Artifact Detection

`src/docxaicorrector/structure/topology.py` currently defines page-furniture
phrases:

- `src/docxaicorrector/structure/topology.py:87`

and emits `candidate_page_artifact_split` as candidate-only diagnostics:

- `src/docxaicorrector/structure/topology.py:494`
- `src/docxaicorrector/structure/topology.py:534`

Binding split units already require `DocumentMapSplitHint` authority:

- `src/docxaicorrector/structure/topology.py:594`

This is the right authority boundary. The missing piece is feeding the same
page-furniture signal upstream into Stage 1 descriptors and prompt instructions.

### Stage 2 Windowing Differs By Mode

Legacy path without `DocumentMap` uses:

```text
max_window_paragraphs = 1800
max_overlap_paragraphs = 50
preview_chars = 600
target_input_tokens = None
```

from `src/docxaicorrector/processing/preparation.py:783`.

AI-first path with `DocumentMap` uses anchored settings:

```text
max_window_paragraphs = 3000
overlap_paragraphs = 0
preview_chars = 1500
target_input_tokens = 180000
```

from `src/docxaicorrector/processing/preparation.py:776`.

`build_structure_map(...)` still iterates descriptor windows:

- `src/docxaicorrector/structure/recognition.py:835`
- `_iter_descriptor_windows(...)` at
  `src/docxaicorrector/structure/recognition.py:1529`

The merge step `_merge_window_classifications(...)` chooses between overlapping
classifications by distance from window edge. It does not perform structural
reasoning such as merging adjacent H1 headings:

- `src/docxaicorrector/structure/recognition.py:1639`

This spec does not change Stage 2 behavior. It adds read-only seam diagnostics so
future window tuning can be evidence-driven.

## Goals

1. Raise Stage 1 document-map preview fidelity within the current config clamp.
2. Make page-furniture contamination and related structural-damage signals
   explicit in Stage 1 descriptors.
3. Reuse a single page-furniture detection library across Stage 1 hints,
   topology candidate operations, display hygiene, and output detectors.
4. Change Stage 1 prompt instructions so PDF-furniture handling is a measurable
   AI responsibility, not implicit behavior.
5. Preserve the AI-first authority boundary: deterministic code extracts signals,
   while `DocumentMap` / topology projection provide structural authority.
6. Add diagnostics that distinguish missing Stage 1 signal visibility from later
   display residue.
7. Add a model-comparison protocol that evaluates quality and runtime stability,
   not just pass/fail.

## Non-Goals

- No final Markdown structural rewrite.
- No automatic adjacent-H1 merge.
- No post-merge AI repair call in this slice.
- No Stage 2 window-size behavior change in this slice.
- No clamp increase above `400` for `structure_recovery_document_map_preview_chars`
  in this slice.
- No new split kind beyond the existing `page_artifact_heading` and
  `compound_toc_entries`.
- No new role taxonomy unless required by a separate approved spec.
- No document-specific phrase additions outside the shared closed phrase library.
- No full-book run as an inner-loop tuning step.

## Design Overview

```text
shared page-furniture detector
  -> ParagraphUnit advisory signals / descriptor hints
  -> Stage 1 DocumentMap prompt payload
  -> DocumentMap split_hints or review_zones
  -> Stage 1.5 topology projection binding only with Stage 1 authority
  -> output display hygiene + detectors consume same phrase library
```

The implementation must avoid creating parallel phrase lists. The existing
`_PAGE_FURNITURE_PHRASES` and related matching logic should be extracted into a
shared module and consumed by all relevant callers.

## Shared Page-Furniture Detection Library

Add a shared module, for example:

`src/docxaicorrector/structure/page_furniture_detection.py`

The module should own:

- closed phrase library;
- whitespace normalization;
- safe casefold matching;
- offset calculation;
- candidate shape classification;
- small dataclass records for detector hits.

Initial public API shape:

```python
from dataclasses import dataclass
from typing import Literal

PageFurnitureKind = Literal[
    "blank_page_marker",
    "intentionally_blank_marker",
    "running_header_candidate",
    "page_number_island",
]

@dataclass(frozen=True)
class PageFurnitureHit:
    kind: str
    phrase: str
    start: int
    end: int
    confidence: str
    reason: str


def find_page_furniture_hits(text: str, *, search_limit: int | None = None) -> tuple[PageFurnitureHit, ...]: ...


def contains_page_furniture(text: str) -> bool: ...
```

The initial closed phrase library must match the current topology intent:

```python
PAGE_FURNITURE_PHRASES = (
    "this page intentionally left blank",
    "эта страница намеренно оставлена пустой",
    "page intentionally left blank",
    "intentionally blank",
    "intentionally left blank",
)
```

Adding a phrase requires tests for:

- Stage 1 descriptor hint emission;
- topology candidate operation behavior;
- display hygiene behavior;
- output detector behavior.

This shared library is authoritative for the companion output spec as well. The
output spec must not introduce extra blank-page phrases before this shared
library contract is expanded in an approved follow-up.

Consumers to migrate:

- `src/docxaicorrector/structure/topology.py`
- `src/docxaicorrector/structure/document_map.py`
- `src/docxaicorrector/pipeline/display_hygiene.py` from the companion spec
- output detector implementation from the companion spec

## Stage 1 Descriptor Additions

Bump `DOCUMENT_MAP_DESCRIPTOR_SCHEMA_VERSION`.

Add deterministic fields to `DocumentMapParagraphDescriptor`. Full semantic
names are listed here; implementation may encode compact prompt keys.

Recommended fields:

```python
contains_page_furniture_phrase: bool
page_furniture_phrase_kinds: tuple[str, ...]
page_furniture_offsets: tuple[tuple[int, int], ...]
contains_blank_page_marker: bool
contains_inline_page_number_island: bool
running_header_candidate: bool
heading_body_concat_candidate: bool
```

Compact prompt key suggestion:

```json
{
  "pf": true,
  "pf_k": ["blank_page_marker"],
  "pf_pos": [[84, 119]],
  "blank": true,
  "pni": false,
  "rh": false,
  "hbc": true
}
```

The signal extractor must not modify `ParagraphUnit.text`. It only exposes
bounded, auditable hints.

### Signal Semantics

`contains_page_furniture_phrase`:

- true when shared page-furniture detection finds a closed-library phrase
  anywhere in the paragraph text, not only in the first preview window.

`page_furniture_offsets`:

- character offsets in the full paragraph text;
- offsets may be omitted or truncated in prompt payload if necessary, but must be
  preserved in debug artifacts.

`contains_blank_page_marker`:

- true for blank-page marker phrases.

`contains_inline_page_number_island`:

- true for short page-number-shaped islands, guarded conservatively;
- diagnostic signal only, not deletion authority.

`running_header_candidate`:

- true when the paragraph or inline island contains repeated page-header-like
  text according to document-level frequency analysis.

`heading_body_concat_candidate`:

- true when a paragraph appears to contain heading-like opening text followed by
  body-sentence continuation;
- diagnostic signal only, not split authority.

## Stage 1 Preview Fidelity

Change default `structure_recovery.document_map.preview_chars` from `120` to
`400`.

Required code/config updates:

- `config.toml` default under `[structure_recovery.document_map]`.
- config defaults in `src/docxaicorrector/core/config_structure_sections.py` if
  applicable.
- tests that assert default config values.
- cache identity already includes `preview_chars` at
  `src/docxaicorrector/processing/preparation.py:804`; keep that behavior.

Do not change the clamp in this slice. Current maximum is `400`, so this slice
uses the existing allowed maximum.

If future evidence shows `400` is insufficient, create a separate slice that:

- raises clamp to `800` or another justified value;
- bumps descriptor/prompt versions;
- validates token-budget fallout;
- records model-specific timeout/runtime effects.

## Token Budget Guard

Increasing preview length can cause `select_document_map_logical_indexes(...)` to
shrink descriptor coverage under `max_input_tokens = 180000`.

Add diagnostics to DocumentMap progress/debug artifacts:

```json
{
  "descriptor_count": 4200,
  "sampled_count_before_token_budget": 4200,
  "sampled_count_after_token_budget": 3880,
  "token_budget_dropped_count": 320,
  "token_budget_dropped_signal_counts": {
    "contains_page_furniture_phrase": 0,
    "heading_body_concat_candidate": 2
  }
}
```

Acceptance for this slice:

- page-furniture signal descriptors must not be dropped by token-budget shrink
  unless the run is explicitly marked degraded;
- if they are dropped, the diagnostic must show exact counts and sample indexes;
- implementation must compare descriptor coverage before/after the preview
  increase on targeted profiles.

If `400` causes unacceptable descriptor loss, the first remediation should be an
ordered sampling priority fix, not broad final Markdown cleanup.

## Ordered Sampling Priority

Replace or wrap the flat `_is_structurally_important_descriptor(...)` boolean with
an ordered priority model used when sampling is required.

Recommended tiers:

1. `hard_structural`: explicit headings, authoritative style cluster / font
   outlier, very large vertical gap.
2. `anchor_structural`: TOC candidates, scripture/reference candidates, isolated
   markers, existing embedded structure hints.
3. `damage_signal`: page-furniture contamination, heading/body concat candidate,
   inline page-number island, running-header candidate.
4. `soft_context`: short text (`text_length < 60`) and uniform sampling context.

Important behavior:

- `damage_signal` must be included before `soft_context`.
- `damage_signal` must not displace `hard_structural` or `anchor_structural` when
  the sample budget is tight.
- Debug artifacts must include sampled counts by tier.

This avoids a flat OR where many blank-page/footer candidates could crowd out
real heading candidates in very large documents.

## Stage 1 Prompt Updates

Bump `DOCUMENT_MAP_PROMPT_VERSION`.

Add instructions to the Stage 1 user/system prompt. The exact wording may differ,
but the following responsibilities must be present:

1. PDF page furniture is non-semantic and must not be included in outline titles.
2. Blank-page markers must not become body, chapter, front-matter, epigraph, or
   attribution content.
3. If one physical paragraph contains page furniture plus a real heading, emit a
   `page_artifact_heading` split hint only when globally supported by nearby body
   or TOC evidence.
4. If one physical TOC paragraph contains multiple ordered entries, use existing
   `compound_toc_entries` split hints; do not shorten body heading canonical
   titles to TOC-only fragments.
5. If the model is uncertain whether a contaminated paragraph is semantic, emit a
   `review_zone` rather than inventing structure.
6. Preserve semantic text order. `DocumentMap` must not delete content; it may
   classify, anchor, split-hint, or review-zone.
7. Use `epigraph` and `attribution` anchors for attribution-shaped material only
   when globally coherent; do not demote headings by name-list patterns.

The prompt must explicitly mention the new descriptor keys and what they mean.

## DocumentMap Schema Behavior

No new split kind is required in this slice.

Existing `page_artifact_heading` should be used when:

- shared page-furniture detection identifies a phrase in a paragraph;
- the remainder or local neighbor matches a globally supported heading target;
- confidence is high enough to bind later in topology projection.

When confidence is insufficient:

- do not emit a speculative binding split hint;
- emit a `review_zone` with evidence referencing page-furniture contamination;
- keep `paragraph_anchors` conservative.

If implementation needs richer evidence without a schema-breaking role change,
prefer adding evidence strings inside existing records over expanding role
vocabulary.

## Stage 2 Seam Diagnostics

This slice does not tune Stage 2 windows. It adds visibility for seam risk.

When `build_structure_map(...)` constructs windows, persist read-only diagnostics:

```json
{
  "stage2_window_count": 2,
  "stage2_windows": [
    {"ordinal": 1, "first_logical_index": 0, "last_logical_index": 2999},
    {"ordinal": 2, "first_logical_index": 3000, "last_logical_index": 3520}
  ],
  "stage2_seams": [3000],
  "near_seam_signal_counts": {
    "adjacent_heading_like_pair": 1,
    "document_map_outline_member": 0,
    "page_furniture_signal": 0
  }
}
```

Near-seam scan:

- window seam logical index +/- `K = 10` paragraphs;
- count adjacent heading-like pairs;
- count paragraphs with page-furniture signals;
- count DocumentMap outline/member indexes near the seam;
- do not change classifications.

Stage 2 overlap/window tuning remains a separate future slice. This diagnostic is
included here because it distinguishes input-fidelity failures from window-seam
visibility failures.

## Input-Fidelity Acceptance Checks

Add diagnostic checks to structural reports. These can start advisory and become
profile-gated later.

### `document_map_page_furniture_signal_visibility`

Purpose: every deterministic page-furniture candidate is visible to Stage 1.

Pass condition for strict profiles:

```text
all page-furniture candidate logical indexes are included in sampled descriptors
and the prompt preview or descriptor signal exposes the contamination
```

Reported fields:

- `candidate_count`
- `sampled_visible_count`
- `missing_from_sample_count`
- `missing_from_preview_count`
- first N samples with logical index, phrase, offsets, preview.

### `document_map_page_artifact_resolution_coverage`

Purpose: candidates with page furniture + local heading evidence must be resolved
by Stage 1 authority or explicitly escalated.

A candidate is covered when at least one is true:

- `DocumentMap.split_hints` contains `split_kind == "page_artifact_heading"` for
  that logical index;
- `DocumentMap.review_zones` includes that logical index with page-furniture
  evidence;
- topology projection emits candidate-only operation and records absence of Stage
  1 authority.

Reported fields:

- `candidate_count`
- `split_hint_count`
- `review_zone_count`
- `candidate_only_topology_count`
- `unresolved_count`

### `structure_model_runtime_stability`

Purpose: compare model changes and preview/window changes against runtime
fallback behavior.

Reported fields:

- `structure_timeout_retry_count`
- `structure_timeout_retry_failed_count`
- `structure_window_split_count`
- `structure_split_fallback_descriptor_count`
- `structure_split_fallback_classified_count`
- `structure_split_fallback_capped_descriptor_count`
- `stage2_window_count`

Strict pass/fail thresholds should be profile-specific. For model-comparison
experiments this check may be advisory but must be reported.

## Model Comparison Protocol

A model swap is not accepted based only on `passed: true`.

For structure model comparison, compare at least:

- `DocumentMap.outline`
- `DocumentMap.toc_region.entries`
- `DocumentMap.split_hints`
- `DocumentMap.review_zones`
- topology projection operations
- projected units
- `outline_coverage_ratio`
- unmapped source/target basis and counts
- output detector counts from the companion output spec
- timeout and split-fallback counters
- cache keys and model IDs used

The `gemini-3.5-flash` exploratory diagnostic already showed why this matters:
it improved a `Chapter Nine: STRATEGIES FOR NGOs` TOC split in one bounded
profile, but also triggered Stage 2 timeout/split fallback. Both facts are
material.

Recommended bounded comparison profiles:

- `lietaer-pdf-first-20-structure-core`
- `lietaer-pdf-chapter-region-core`
- `end-times-pdf-core` when page-furniture behavior is in scope

Full-book benchmark runs are milestone evidence, not tuning-loop evidence.

## Implementation Plan

### Phase 0: Extract Shared Page-Furniture Detection

Files likely affected:

- `src/docxaicorrector/structure/page_furniture_detection.py`
- `src/docxaicorrector/structure/topology.py`
- tests for topology candidate page-artifact operations

Work:

1. Move `_PAGE_FURNITURE_PHRASES` and phrase matching helpers into a shared
   module.
2. Keep topology behavior unchanged.
3. Add tests proving topology candidate operations still use the same phrases.

Acceptance:

- No behavior change in topology candidate operations.
- One phrase library is imported by topology; no duplicated list remains there.

### Phase 1: Stage 1 Descriptor Signals

Files likely affected:

- `src/docxaicorrector/structure/document_map.py`
- `src/docxaicorrector/core/models.py` only if shared descriptor models require it
- tests for document-map descriptor payloads and schema versioning

Work:

1. Add page-furniture and damage-signal fields to
   `DocumentMapParagraphDescriptor`.
2. Populate fields from shared detector without mutating paragraph text.
3. Bump `DOCUMENT_MAP_DESCRIPTOR_SCHEMA_VERSION`.
4. Include signals in debug artifacts.

Acceptance:

- A paragraph containing `This page intentionally left blank` after character 120
  still has `contains_page_furniture_phrase = true`.
- Descriptor prompt payload includes compact signal keys.
- Descriptor schema version changes cache identity.

### Phase 2: Preview Fidelity To 400

Files likely affected:

- `config.toml`
- `src/docxaicorrector/core/config_structure_sections.py` defaults if needed
- config-loader tests
- document-map cache-key tests

Work:

1. Change default `structure_recovery.document_map.preview_chars` from `120` to
   `400`.
2. Do not raise the clamp above `400`.
3. Add before/after diagnostic coverage tests for long contaminated paragraphs.
4. Add token-budget coverage diagnostics.

Release note for rollout: companion output-spec thresholds remain advisory until
this spec completes Phase 5 diagnostics and acceptance checks.

Acceptance:

- Config resolves default preview as `400`.
- Long contaminated paragraph fixture exposes both preview text and explicit
  page-furniture signal.
- Token-budget diagnostic reports before/after sampled counts.

### Phase 3: Ordered Sampling Priority

Work:

1. Replace flat importance selection with ordered tiers when sampling is required.
2. Ensure damage-signal descriptors are retained before soft short-text context.
3. Add sampled counts by tier to debug artifacts.

Release note for rollout: do not tighten companion output-spec thresholds while
sampling priority can still starve newly added damage-signal descriptors.

Acceptance:

- In a synthetic >limit fixture, hard structural and anchor structural candidates
  are retained before damage signals.
- Damage signals are retained before short-text-only soft context.
- Token-budget shrink reports any dropped damage-signal descriptors.

### Phase 4: Prompt Responsibility Update

Work:

1. Update DocumentMap prompt wording for PDF-furniture contamination.
2. Bump `DOCUMENT_MAP_PROMPT_VERSION`.
3. Add tests for prompt contents and version/cache invalidation.

Acceptance:

- Prompt mentions page-furniture descriptor keys.
- Prompt instructs split hint vs review zone behavior.
- Existing compound TOC behavior remains covered.

### Phase 5: Diagnostics And Acceptance Checks

Work:

1. Add `document_map_page_furniture_signal_visibility`.
2. Add `document_map_page_artifact_resolution_coverage`.
3. Add `structure_model_runtime_stability`.
4. Add Stage 2 seam diagnostics as read-only artifacts/report fields.

Acceptance:

- Checks are advisory unless profile thresholds require strict behavior.
- Structural diagnostic report contains candidate counts and samples.
- Model-comparison output can compare quality and runtime stability.

## Test Plan

Unit tests:

- shared detector finds EN/RU page-furniture phrases;
- shared detector returns offsets for phrases after character 120;
- topology candidate page-artifact operation behavior is unchanged after shared
  detector extraction;
- DocumentMap descriptors include page-furniture signals;
- descriptor schema version and prompt version bumps invalidate cache identity;
- ordered sampling preserves hard structural before damage-signal before soft
  context;
- token-budget shrink reports dropped signal counts;
- Stage 2 seam diagnostic reports seam locations and near-seam signal counts.

Focused structural diagnostics:

```bash
bash scripts/run-structural-preparation-diagnostic.sh lietaer-pdf-first-20-structure-core
bash scripts/run-structural-preparation-diagnostic.sh lietaer-pdf-chapter-region-core
bash scripts/run-structural-preparation-diagnostic.sh end-times-pdf-core
```

Use the canonical WSL/runtime rules from `AGENTS.md`. For model-comparison runs,
record both model selectors and all runtime fallback counters.

## Rollout And Safety

- Roll out descriptor signals before strict checks.
- Keep checks advisory until fixture baselines are reviewed.
- Companion output-spec thresholds must stay advisory until this spec Phase 5
  lands and baselines are refreshed with the new Stage 1 signals.
- Do not broaden final Markdown cleanup to make new checks pass.
- If preview `400` causes token-budget descriptor loss, fix sampling/metadata
  before raising final-output cleanup scope.
- If a stronger model improves split hints but regresses runtime stability, do not
  switch globally; consider role-specific model assignment or bounded profiles.

## Future Work

Separate specs should cover:

- adjacent-H1 post-merge AI repair;
- Stage 2 window overlap or full-document anchored classification tuning;
- clamp increase above `400` for Stage 1 preview;
- topology-side remediation for heading/body boundary repair;
- epigraph/attribution classification improvements with `DocumentMap` authority.
