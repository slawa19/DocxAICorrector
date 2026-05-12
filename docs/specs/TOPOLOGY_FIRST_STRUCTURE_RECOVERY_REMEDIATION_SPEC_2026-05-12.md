# Topology-First Structure Recovery Remediation Spec

Date: 2026-05-12
Status: Proposed
Parent spec: `docs/AI_FIRST_STRUCTURE_RECOVERY_SPEC_2026-05-08.md`
Related follow-up: `docs/specs/Folloup AI structure recovery.md`

## Problem Statement

The current `lietaer-pdf-full-benchmark` work has reached diminishing returns. The
latest iterations improved isolated symptoms, but the full-book structural gate
still fails on the same classes:

- `unmapped_source_threshold`
- `unmapped_target_threshold`
- `no_toc_body_concat_required`

Recent deterministic fixes did produce local wins:

- bounded TOC propagation now reaches the structural snapshot;
- `DocumentMap` now recovers Chapter 9 in TOC/body anchors;
- final markdown normalization can split `This page intentionally left blank Chapter ...`;
- false fragment heading count decreased on the latest full rerun.

But the same expensive rerun also showed that these are not the core issue:

- `toc_body_concat_detected` remained `true`;
- `list_fragment_regression_count` remained flat;
- `unmapped_source_count` regressed from `129` to `132`;
- source-side diagnostics still contain `this page intentionally left blank chapter nine`;
- composite heading fragments such as `the citizens`, `an ancient future?`, and
  `democracy, transparency,` are still treated as standalone structural units.

This means the current work is drifting into the anti-pattern explicitly called
out by the parent spec: adding pattern-specific deterministic cleanup after the
AI-first stages instead of giving the AI-first structure authority enough power
to correct global document topology.

## Verified Current-State Evidence

### Markdown Postprocessor Stack

The current dirty implementation imports and applies multiple output-level
normalizers in `src/docxaicorrector/pipeline/late_phases.py`:

- `normalize_page_placeholder_heading_concats_markdown`
- `normalize_false_fragment_headings_markdown`
- `normalize_residual_bullet_glyphs_markdown`
- `normalize_list_fragment_regressions_markdown`
- `normalize_mixed_script_markdown`

`src/docxaicorrector/pipeline/output_validation.py` also exposes
`has_toc_body_concat_markdown(...)`, which still judges TOC/body concat through
markdown text. The latest placeholder-specific normalizer is a narrow regex for
`this page intentionally left blank` followed by `chapter|глава`.

This confirms the concern: structure defects are being corrected in final
markdown and quality paths, after paragraph topology, Stage 1 `DocumentMap`,
Stage 2 classification, Stage 3 reconciliation, and restore/mapping diagnostics
have already happened.

### Parent Spec Guardrail Conflict

The parent spec's `Forbidden implementation direction` says agents must not fix
structure-recovery defects by adding document-specific or pattern-specific
heuristics that assign final structural facts. It explicitly forbids exceptions
for one PDF title, TOC phrase, font pattern, scripture/reference shape, or
chapter-name format.

The latest placeholder fix is narrower and safer than most legacy heuristics,
but architecturally it is still a symptom fix in the final markdown layer. It
cannot repair source-side topology, which is why the full rerun still shows the
source artifact `this page intentionally left blank chapter nine` in formatting
diagnostics.

### AI-First Contract Gap

The existing AI-first architecture gives Stage 1 authority over:

- `body_start_logical_index`
- `toc_region`
- `outline`
- `paragraph_anchors`
- `review_zones`

Stage 3 can patch roles via `StructureMap`, but it does not change paragraph
boundaries or semantic grouping. Therefore, when PDF extraction splits a single
semantic heading into multiple `ParagraphUnit`s, the AI can only classify each
fragment; it cannot repair the topology that made those fragments separate in
the first place.

This is visible in the Lietaer full-book residuals:

```text
Governance and We,
the citizens
an ancient future?
```

The correct unit is one chapter title, but the current system sees multiple
paragraph units. Stage 2 may classify each short line as a heading, and Stage 3
can only patch roles, not merge them into one authoritative structural unit.

### Gate Mismatch

The failed full-book checks are still computed from downstream proxies rather
than from the AI-first structural authority:

- `no_toc_body_concat_required` ultimately depends on markdown detection through
  `has_toc_body_concat_markdown(...)`;
- `unmapped_*` thresholds depend on restore/reassembly mapping diagnostics;
- list-fragment regressions are detected in output text, not in a structure-aware
  notes/bibliography topology.

As a result, a real Stage 1 improvement, such as recovering Chapter 9, may not
move the failing gate. The gate is measuring final artifacts and mapping drift,
while the AI-first system improves structure artifacts.

## Architectural Diagnosis

The core problem is not one missing regex. The core problem is that the pipeline
still treats final `ParagraphUnit[]` as immutable topology before the global AI
structure pass has authority to revise it.

Current shape:

```text
PDF/DOCX
  -> extraction/boundaries/layout repair create ParagraphUnit[]
  -> Stage 1 DocumentMap over existing topology
  -> Stage 2 paragraph classification
  -> Stage 3 role reconciliation only
  -> markdown/output cleanup
  -> quality gates over output proxies
```

Required shape:

```text
PDF/DOCX
  -> extraction emits physical units and signals
  -> Stage 1 DocumentMap builds global document authority
  -> Stage 1.5 topology projection repairs groups/splits/merges from that authority
  -> Stage 2 classifies the repaired topology
  -> Stage 3 reconciles roles and groups
  -> gates read structure/topology artifacts first
  -> markdown is rendered from structural units, not repaired afterward
```

## Proposed Direction

Adopt a topology-first remediation slice. This is a deliberate architectural
fork from the current pattern of output markdown normalization.

The remediation has three linked moves:

1. **R1: Stage 1.5 DocumentMap Topology Projection**
2. **R2: Structure-Aware Quality Gates**
3. **R3: Markdown Postprocessor Retirement Plan**

These moves can be implemented incrementally, but they should be tracked as one
architecture change because each one reinforces the same authority boundary.

## R1: Stage 1.5 DocumentMap Topology Projection

### Goal

Give Stage 1 authority over paragraph boundary repairs that are global in
nature, without returning to heuristic-first mutation.

### New Concept

Introduce a topology projection stage after Stage 1 and before Stage 2:

```python
apply_document_map_topology(
    paragraphs: list[ParagraphUnit],
    document_map: DocumentMap,
    *,
    app_config: Mapping[str, Any],
) -> DocumentTopologyProjection
```

The projection is deterministic, audited, and bounded. It does not invent
structure from regex alone; it projects explicit Stage 1 `DocumentMap` authority
and validated signals onto the paragraph topology.

### Authority Model

Topology projection uses **Stage 1 authority first**. This is a hard boundary,
not an implementation preference.

For split operations, the chosen contract is **Variant A**:

- Stage 1 must expose explicit topology intent before a split is applied.
- Projection may validate and materialize that intent, but it must not discover
  final split boundaries from regex alone.
- Regex/text patterns are allowed only as validators for a Stage 1 hint or as
  signal extraction recorded in diagnostics.

This requires extending `DocumentMap` with explicit topology hints before
`split_page_artifact_from_heading` and `split_compound_toc_entries` are allowed
to affect structural readiness:

```python
@dataclass(frozen=True)
class DocumentMapSplitHint:
    logical_index: int
    split_kind: str  # page_artifact_heading | compound_toc_entries
    expected_parts: tuple[str, ...]
    authority: str
    confidence: str
    evidence: tuple[str, ...] = ()
```

Until this field exists and is populated by Stage 1, split operations may be
reported as candidates but must not become binding topology operations.

### Configuration And Feature Flags

Topology projection is an opt-in path. It must follow the parent spec's rollback
discipline: a single config flag must restore legacy behavior without redeploy.

Minimum new `config.toml` keys (parsed in
`src/docxaicorrector/core/config_structure_sections.py` with matching
`DOCX_AI_STRUCTURE_RECOVERY_TOPOLOGY_*` env overrides):

```toml
[structure_recovery.topology_projection]
enabled = false
save_debug_artifacts = true
binding_splits_enabled = false
```

Note: the topology projection schema version is a module constant
(`TOPOLOGY_PROJECTION_SCHEMA_VERSION` in
`src/docxaicorrector/structure/topology.py`), not a user-facing config key.
Exposing it as configuration would let env overrides change cache/artifact
contracts without a corresponding code change.

Semantics:

- `enabled = false`: legacy behavior. No `DocumentTopologyProjection` is built,
  Stage 2 descriptors are byte-compatible with today's output, and gates use
  the existing markdown/paragraph paths.
- `enabled = true` and `binding_splits_enabled = false`: projection runs and
  emits `merge_heading_continuation` units; split operations are recorded as
  candidate-only diagnostics. This is the Phase 2 target state.
- `binding_splits_enabled = true`: Phase 3 target state. Requires Stage 1
  `split_hints` schema and prompt version to be in place.

`structure_recovery.enabled = false` from the parent spec must continue to
disable everything in this remediation spec as well, including projection,
splits, and structure-aware gates.

### Integration Surfaces

"Sidecar projection" is a data-shape decision, not an integration excuse. The
following attachment points must be explicit in the implementation:

- Prepared-result object: add a `document_topology_projection: DocumentTopologyProjection | None`
  field next to the existing `document_map` field on the prepared/result
  structure used by `processing/preparation.py`.
- Event log: emit a `document_topology_projection_built` event with operation
  counts, unit counts by `unit_type`, and `authority` distribution. Add a
  `document_topology_projection_skipped` event with reason when projection is
  disabled, fails validation, or finds no operations.
- Diagnostic snapshot (`run-structural-preparation-diagnostic.sh` output): add a
  `document_topology_projection` section mirroring the persisted artifact, with
  the same closed-vocabulary fields.
- Stage 2 descriptor builder: extend
  `build_paragraph_descriptors(...)` to accept `topology_projection` and
  attach unit fields per the Stage 2 Descriptor Contract below. Existing
  callers passing only `document_map` remain valid.
- Reconciliation: extend `reconcile_with_document_map(...)` to accept the
  projection and use the unit-coverage rule defined below. Existing callers
  passing only paragraphs and `DocumentMap` remain valid.
- Structural validation / quality report: extend
  `validation/structural.py` to read projection-aware fields. When projection
  is absent, fall back to today's paragraph-level computations.
- Restore/reassembly diagnostics: extended in Phase 4 to compute unit-keyed
  coverage alongside raw paragraph coverage.

### Fallback Behavior

When `DocumentTopologyProjection` is absent or projection is disabled, the
implementation must guarantee:

- Stage 2 descriptor payloads are byte-compatible with today's output. The
  structure-map cache key may still include topology schema/fingerprint inputs
  to prevent stale anchored caches from being reused after schema bumps; this
  is a cache-key concern, separate from descriptor payload shape.
- `reconcile_with_document_map(...)` uses today's paragraph-level outline
  coverage path.
- Structural gates use today's markdown/paragraph signals.
- Markdown postprocessors continue to run unchanged. R3 retirement is not
  triggered.
- No new `.run/document_topology/` artifact is written.

A single explicit code path must enforce this. "Implicit equivalence" by
testing feature flags in many places is not acceptable.

### New Artifact

Persist a debug artifact under a new directory:

```text
.run/document_topology/<cache_key>.json
```

Suggested payload:

```json
{
  "stage": "document_topology_projection_v1",
  "schema_version": 1,
  "cache_key": "...",
  "document_map_cache_key": "...",
  "topology_projection_schema_version": 1,
  "operations": [
    {
      "op": "merge_heading_continuation",
      "logical_indexes": [1004, 1005, 1006, 1007],
      "canonical_text": "Chapter Eleven Governance and We, the Citizens: An Ancient Future?",
      "authority": "document_map_outline",
      "confidence": "high",
      "evidence": ["outline_entry", "adjacent_short_heading_fragments"]
    }
  ],
  "projected_units": []
}
```

Cache-key derivation must include at minimum:

- `document_map_cache_key` or the equivalent Stage 1 cache fingerprint;
- `topology_projection_schema_version`;
- the Stage 1 topology-hint schema version;
- the ordered `ParagraphUnit.logical_index` / text-preview fingerprint used by
  projection.

Additionally, introducing `split_hints` (or any new authoritative field) into
`DocumentMap` requires bumping the existing `DocumentMap` cache fingerprint /
prompt version. Old maps cached without the field must not be reused as binding
authority for new projection paths, because the absence of the field is then
indistinguishable from "Stage 1 explicitly emitted no hints".

Artifact retention must be added to `docs/LOGGING_AND_ARTIFACT_RETENTION.md` and
implemented through `runtime_artifact_retention.prune_artifact_dir(...)` before
the new writer is merged. Use the same default family as structure artifacts
unless a stronger reason is documented: TTL 30 days, max 200 files.

### Operation Types

Start with three operation types only:

1. `merge_heading_continuation`
2. `split_page_artifact_from_heading`
3. `split_compound_toc_entries`

Do not include bibliography, URL tails, or general list repair in the first
slice. Those are separate structural regions and should be handled after chapter
and TOC topology become stable.

### Operation: `merge_heading_continuation`

Purpose: repair composite headings split into multiple physical paragraphs.

Examples:

```text
Chapter Eleven
Governance and We,
the Citizens
An Ancient Future?
```

or:

```text
Governance and We,
the citizens
an ancient future?
```

Rules:

- The operation must be anchored to a high-confidence `DocumentMap` outline or
  TOC body candidate.
- Candidate continuation fragments must be adjacent or within a small bounded
  window, for example 1-3 following paragraphs.
- Candidate fragments must be short and heading-like, but regex alone is not
  sufficient authority; the expected canonical title must come from
  `DocumentMap`/TOC/outline context.
- The projection must record which physical logical indexes were grouped.

### Operation: `split_page_artifact_from_heading`

Purpose: handle page furniture concatenated with real headings before markdown.

Example:

```text
this page intentionally left blank chapter nine
```

Expected projection:

```text
page_artifact: this page intentionally left blank
heading: chapter nine
```

Rules:

- The heading tail must match an expected `DocumentMap` outline or TOC entry
  candidate in the local neighborhood.
- A binding split requires a high-confidence `DocumentMapSplitHint` with
  `split_kind == "page_artifact_heading"` for the same `logical_index`.
- Without that hint, the implementation may emit a diagnostic candidate only;
  it must not change structural gate inputs.
- The page-artifact component must be classified as furniture/noise, not emitted
  as a body paragraph that can become `unmapped_target` noise.
- The output markdown normalizer must no longer be the primary fixer for this
  case once topology projection is active.

### Operation: `split_compound_toc_entries`

Purpose: repair over-merged TOC lines before the TOC/body concat gate.

Example:

```text
73 6 Strategies for Banking 95 7 Strategies for Business and Entrepreneurs 119 8 Strategies for Governments 141 9 Strategies for NGOs
```

Expected projection:

```text
TOC entry: 6 Strategies for Banking, page 73/95 depending source convention
TOC entry: 7 Strategies for Business and Entrepreneurs
TOC entry: 8 Strategies for Governments
TOC entry: 9 Strategies for NGOs
```

Rules:

- Apply only inside the bounded `DocumentMap.toc_region`.
- A binding split requires either a high-confidence `DocumentMapSplitHint` with
  `split_kind == "compound_toc_entries"` or an existing high-confidence
  `DocumentMap.toc_region.entries` list that maps one-to-one to the projected
  TOC entry parts.
- If projected parts cannot be matched one-to-one to `DocumentMapTocEntry`
  titles/candidates, report `compound_toc_split_unresolved` and leave the gate
  conservative.
- Preserve provenance through `origin_raw_indexes` and original logical indexes.
- Do not create standalone body headings from TOC fragments.

Clarification: a one-to-one match against high-confidence
`DocumentMap.toc_region.entries` is treated as an **implicit Stage 1 split
authority** and remains within Variant A. It is not a regex fallback path. The
authority comes from Stage 1's structured TOC entries; the projection only
materializes them into separate `toc_entry` units. This dual path exists because
Stage 1 may express TOC topology either as an explicit `DocumentMapSplitHint` or
as a populated `toc_region.entries` list, and both are AI-authored.

### Data Model Options

Prefer non-destructive grouping first. Do not immediately rewrite every consumer
to use a new paragraph list.

Suggested first implementation:

```python
@dataclass(frozen=True)
class StructuralUnit:
    unit_id: str
    unit_type: str  # closed vocabulary, see below
    logical_indexes: tuple[int, ...]
    canonical_text: str
    role: str
    heading_level: int | None
    confidence: str
    authority: str  # closed vocabulary, see below
    evidence: tuple[str, ...]  # closed vocabulary, see below
```

`unit_id` must be stable across runs for the same projected unit. Use a stable
hash of `(unit_type, logical_indexes, canonical_text)` rather than a sequence
number, for example `u_<sha1[:12]>`.

Initial closed vocabularies:

- `unit_type`: `chapter_heading`, `section_heading`, `toc_entry`,
  `page_artifact`, `body`, `unknown`.
- `authority`: `document_map_outline`, `document_map_toc`,
  `document_map_review_zone`, `document_map_anchor`, `document_map_split_hint`.
- `evidence`: `outline_entry`, `toc_entry`, `split_hint`,
  `adjacent_short_heading_fragments`, `local_heading_neighborhood`,
  `bounded_toc_region`, `page_artifact_phrase`, `one_to_one_toc_entry_match`.

Adding vocabulary values requires a schema-version bump and a test proving the
new value is serialized and consumed correctly.

`ParagraphUnit` can then carry optional projection fields, or downstream code can
consume a sidecar `DocumentTopologyProjection` keyed by `logical_index`.

A destructive paragraph-list rewrite should be a later slice only if the sidecar
projection is insufficient.

### Stage 2 Descriptor Contract

Stage 2 must see topology projection. Otherwise Stage 1.5 becomes a third source
of truth and the local classifier can recreate the same standalone fragment
headings that projection just grouped.

`build_paragraph_descriptors(...)` must change signature to accept an optional
projection:

```python
build_paragraph_descriptors(
    paragraphs: list[ParagraphUnit],
    *,
    document_map: DocumentMap | None = None,
    topology_projection: DocumentTopologyProjection | None = None,
    preview_chars: int = ...,
) -> list[ParagraphDescriptor]
```

`ParagraphDescriptor.to_prompt_dict(...)` adds topology fields when a projection
is present:

```json
{
  "unit_id": "u_ab12cd34ef56",
  "unit_type": "chapter_heading",
  "unit_role": "heading",
  "unit_heading_level": 1,
  "unit_canonical_text": "Chapter Eleven Governance and We, the Citizens: An Ancient Future?",
  "unit_member_count": 4
}
```

Stage 2 prompt instructions must explicitly say that paragraphs sharing a
binding `unit_id` are one structural unit. Continuation members of a heading unit
must not be promoted into competing standalone headings.

### Stage 3 Reconciliation Contract

`reconcile_with_document_map(...)` currently checks outline coverage by
`logical_index`. With topology projection, outline coverage is satisfied if:

- `DocumentMapOutlineEntry.logical_index == L`; and
- there is a `StructuralUnit` with `unit_type in {"chapter_heading", "section_heading"}`;
- and `L in unit.logical_indexes`;
- and the reconciled `StructureMap` does not contradict that unit's binding
  role/level.

Direct paragraph-level matching remains the compatibility path when no topology
projection is present.

## R2: Structure-Aware Quality Gates

### Goal

Make structural gates observe the AI-first structural authority rather than
parallel markdown regex proxies.

### Replace TOC/Body Concat Gate

Current problematic shape:

```text
has_toc_body_concat_markdown(final_markdown)
```

Proposed structure-first gate:

```python
has_toc_body_concat_structure(
    document_map: DocumentMap | None,
    structure_map: StructureMap | None,
    topology_projection: DocumentTopologyProjection | None,
    paragraphs: Sequence[ParagraphUnit],
) -> StructureGateSignal
```

The gate should fail when:

- a `DocumentMap.toc_region` is unbounded or overlaps a body heading;
- a projected TOC entry group includes body paragraphs;
- a body heading anchor lives inside the TOC region after topology projection;
- a compound TOC paragraph could not be split and still contains multiple entry
  signatures.

The gate should not fail merely because final markdown happens to contain a
regex-like pattern that the structure map already classified as TOC or page
furniture.

### Reframe Unmapped Thresholds

Unmapped thresholds should account for structural authority.

Important limitation: bucket exclusions alone do **not** solve the current
full-book `unmapped_source` regression. Composite heading fragments such as
`the citizens` and `an ancient future?` are real source text, not page furniture
or front-matter noise. They only stop counting as standalone unmapped fragments
when R1 groups them into a `StructuralUnit` and restore/reassembly diagnostics
can aggregate coverage by `unit_id`.

When computing structural quality, exclude or separately bucket unmapped units
that are:

- page furniture / repeated headers / repeated footers;
- likely page numbers;
- front matter body advisories;
- `DocumentTopologyProjection` page artifacts;
- TOC entries already represented in a bounded TOC unit;
- notes/bibliography tails once a notes topology slice exists.

The quality report can still expose raw `unmapped_source_count` and
`unmapped_target_count`, but structural gate decisions must use a
structure-adjusted count with the excluded buckets visible in diagnostics.

### Restore/Mapping Unit Aggregation

R2 must update restore/reassembly diagnostics to understand topology projection.
For structural reports, coverage must be computed at both levels:

- raw physical paragraph coverage, preserving today's `logical_index` and
  paragraph-level diagnostics;
- projected structural-unit coverage, keyed by `StructuralUnit.unit_id`.

A heading continuation member is considered covered when its containing
`StructuralUnit` is covered by the restored output. Without this aggregation,
R1 can correctly group composite headings while `unmapped_source_threshold` still
fails on the old physical fragments.

Required diagnostic fields (symmetric on source and target sides):

```json
{
  "raw_unmapped_source_count": 132,
  "structure_unit_unmapped_source_count": 98,
  "unit_covered_source_fragment_count": 3,
  "unmapped_source_count_basis": "structural_unit",
  "raw_unmapped_target_count": 103,
  "structure_unit_unmapped_target_count": 76,
  "unit_covered_target_fragment_count": 2,
  "unmapped_target_count_basis": "structural_unit"
}
```

Both `unmapped_source_threshold` and `unmapped_target_threshold` gates must use
the `structural_unit` basis when topology projection is present; the raw counts
remain as observability-only fields.

### Required Diagnostics

Add explicit fields to the preparation diagnostic snapshot and gate report:

```json
{
  "raw_unmapped_source_count": 132,
  "structure_adjusted_unmapped_source_count": 87,
  "excluded_page_artifact_unmapped_count": 4,
  "excluded_toc_unmapped_count": 12,
  "excluded_front_matter_advisory_count": 3,
  "toc_body_concat_structure_detected": false,
  "toc_body_concat_markdown_detected": true,
  "toc_body_concat_gate_source": "structure"
}
```

This keeps observability while moving authority to structure.

## R3: Markdown Postprocessor Retirement Plan

### Goal

Stop adding structural fixes in final markdown normalization.

### Policy

The following functions should become either diagnostic-only or be retired after
R1/R2 cover their structural roots:

- `normalize_false_fragment_headings_markdown`
- `normalize_list_fragment_regressions_markdown`
- `normalize_page_placeholder_heading_concats_markdown`

The following may remain as non-structural text hygiene only if explicitly scoped:

- `normalize_residual_bullet_glyphs_markdown`
- `normalize_mixed_script_markdown`

Even for retained text hygiene, those functions must not influence structural
readiness gates.

### Transitional Rule

During migration, markdown detectors may remain as advisory fields:

```json
{
  "markdown_toc_body_concat_detected": true,
  "structure_toc_body_concat_detected": false,
  "quality_gate_source": "structure",
  "markdown_signal_status": "advisory"
}
```

A markdown advisory must not fail a structure profile when structure authority is
present and passes.

### Rendering Scope

R3 does **not** require a full markdown rendering rewrite in this slice.

The near-term contract is narrower:

- rendering may remain paragraph-based;
- rendering and quality code may consult `DocumentTopologyProjection` through a
  lookup by `logical_index` / `unit_id`;
- structural markdown postprocessors must stop being readiness authority;
- a future full `StructuralUnit` renderer is a separate follow-up spec, not a
  hidden requirement of Phase 5.

If a full unit-based renderer is later needed, create a separate Phase 6 spec
covering formatting transfer, DOCX style preservation, image/table placeholders,
and restore/mapping diagnostics.

## Explicit Non-Goals For This Slice

- No general bibliography/endnote repair yet.
- No OCR or PDF backend replacement.
- No broad role taxonomy expansion.
- No UI redesign.
- No full rewrite of `ParagraphUnit` identity.
- No new document-specific regex branch for `the citizens`, `an ancient future?`,
  `2011.`, URL tails, or `ibid.`.

## Implementation Plan

### Phase 0: Freeze Symptom Fixing

- Do not add another markdown structural postprocessor.
- Do not add a special-case regex for `Governance and We, the Citizens`.
- Keep existing dirty placeholder fix only as a transitional safety net until R1
  handles the source-side topology case.
- Exit criterion: remove structural use of
  `normalize_page_placeholder_heading_concats_markdown` after
  `split_page_artifact_from_heading` is binding, tested, and reported in
  topology projection artifacts. Until then it remains advisory/compatibility
  cleanup only, not structural proof.
- Prerequisite for Phase 2: register `lietaer-pdf-chapter-region-core` in
  `corpus_registry.toml` covering Chapter 8–11 and the over-merged TOC region.
  Without it, late-book topology cases can only be verified through full-book
  reruns, which violates the inner-loop rule from the parent spec.

### Phase 1a: DocumentMap Split Hint Schema

Narrow, schema-only slice. No projection, no Stage 2 change, no gate change.

Files likely affected:

- `src/docxaicorrector/core/models.py` (add `DocumentMapSplitHint`, add
  `split_hints: tuple[DocumentMapSplitHint, ...]` to `DocumentMap`).
- `src/docxaicorrector/structure/document_map.py` (serialization,
  deserialization, output validation accepting an empty list by default,
  bumped Stage 1 prompt version and cache fingerprint).
- `prompts/document_map_system.txt` (allow-list the new field; the prompt may
  instruct the model to emit an empty list until Phase 3).
- Targeted unit tests for schema, defaults, validation rejection of malformed
  hints, and round-trip serialization.

Acceptance:

- `DocumentMap` round-trips through JSON with and without `split_hints`.
- Stage 1 output validation rejects unknown `split_kind` and out-of-range
  `logical_index` values.
- The `DocumentMap` cache fingerprint is bumped; old cached maps are not
  reused as authority for any later binding split path.
- No downstream behavior change.

### Phase 1: Add Topology Projection Models And Artifact

Files likely affected:

- `src/docxaicorrector/core/models.py`
- new `src/docxaicorrector/structure/topology.py`
- `src/docxaicorrector/processing/preparation.py`
- tests under `tests/test_structure_topology.py` or equivalent

Acceptance:

- Pure unit tests can construct paragraphs and a `DocumentMap`, then assert
  projected units and operations without invoking AI.
- No behavior change to Stage 2 yet unless the feature flag is enabled.
- The artifact writer uses a schema-versioned cache key and has retention
  documented in `docs/LOGGING_AND_ARTIFACT_RETENTION.md`.
- `DocumentMapSplitHint` schema (delivered in Phase 1a) is consumed here only
  as a no-op placeholder field; binding split behavior is still gated to
  Phase 3.
- A pure unit test asserts that `StructuralUnit.unit_id` is a stable hash of
  `(unit_type, logical_indexes, canonical_text)` and does not depend on
  iteration order or run sequence.
- Feature flags `structure_recovery.topology_projection.enabled` and
  `structure_recovery.topology_projection.binding_splits_enabled` are wired
  through `core/config_structure_sections.py` with env overrides and clamps,
  covered by config-loader tests in the existing style.

### Phase 2: Project Chapter Heading Groups

Implement `merge_heading_continuation` from `DocumentMap` outline/TOC authority.

Targeted cases:

- `Chapter Eleven` + `Governance and We,` + `the Citizens` + `An Ancient Future?`
- existing Chapter 9 recovery path must continue to work;
- continuation fragments must not become standalone headings in projected units.

Acceptance:

- `the citizens` and `an ancient future?` are represented as continuation
  members of one heading unit, not independent structural headings.
- The projection is audited in `.run/document_topology/...`.
- Stage 2 descriptors include `unit_id` and unit canonical text for projected
  heading members.
- Reconciliation considers an outline entry covered when its logical index is a
  member of the projected heading unit.
- On `lietaer-pdf-full-benchmark`, the late checkpoint must show a lower
  `structure_unit_unmapped_source_count` than the raw baseline for the affected
  composite-heading fragments after Phase 4 restore/mapping aggregation is in
  place. Before Phase 4, Phase 2 acceptance is limited to projection correctness,
  descriptor propagation, and reconciliation coverage.
- The number of `chapter_heading` structural units should match high-confidence
  `DocumentMap.toc_region.entries` for body chapters within a small documented
  tolerance. Initial tolerance: plus/minus 1 for front-matter/part-title noise.

### Phase 3: Project Page Artifacts And TOC Entries

Implement:

- `split_page_artifact_from_heading`
- `split_compound_toc_entries`

Files likely affected:

- `prompts/document_map_system.txt` (instruct Stage 1 to emit `split_hints` for
  `page_artifact_heading` and `compound_toc_entries` cases);
- `src/docxaicorrector/structure/document_map.py` (Stage 1 output validation
  for non-empty `split_hints`, bump prompt version);
- `src/docxaicorrector/structure/topology.py` (binding split logic);
- `src/docxaicorrector/processing/preparation.py` (wire projection into
  preparation flow).

Acceptance:

- `this page intentionally left blank chapter nine` becomes a page artifact plus
  heading authority before markdown rendering.
- Over-merged TOC paragraphs inside `DocumentMap.toc_region` become multiple TOC
  units before the TOC/body gate.
- Binding split operations are rejected unless backed by `DocumentMapSplitHint`
  or one-to-one high-confidence `DocumentMapTocEntry` matching, as defined in R1.
- Stage 1 prompt version is bumped together with the `DocumentMap` cache
  fingerprint so old cached maps without `split_hints` are not reused as
  binding authority.

### Phase 4: Structure-Aware Gates

Add structure-first gate calculations while preserving raw legacy metrics.

Files likely affected:

- `src/docxaicorrector/validation/structural.py`
- `src/docxaicorrector/pipeline/output_validation.py`
- `src/docxaicorrector/pipeline/late_phases.py`
- real-document validation report serializers

Acceptance:

- Structural diagnostic reports both markdown and structure signals.
- Structure profiles fail/pass based on structure-aware gate fields when
  `DocumentMap` and topology projection are present.
- Legacy/full-output profiles may continue exposing markdown advisory signals.
- Restore/reassembly diagnostics expose raw paragraph coverage and projected
  unit coverage side by side.

### Phase 5: Retire Structural Markdown Normalizers

Once R1/R2 are green on structural diagnostics:

- remove structural use of markdown postprocessors;
- keep only non-structural text hygiene where justified;
- update tests that currently assert markdown cleanup as structural proof.

## Verification Strategy

Follow the repository runtime contract. Use WSL canonical commands.

Inner loop:

```bash
bash scripts/test.sh tests/test_structure_topology.py -q
bash scripts/test.sh tests/test_document_map.py -q
bash scripts/test.sh tests/test_structure_reconciliation.py -q
bash scripts/test.sh tests/test_structure_validation.py -q
```

Structure diagnostic loop:

```bash
bash scripts/run-structural-preparation-diagnostic.sh lietaer-pdf-first-20-structure-core
```

The first-20 profile is not sufficient for this remediation's late-book heading
and TOC cases. Before Phase 2 real-document verification begins, add or register
a cheap chapter region profile that includes the Chapter 8-11 area, for example:

```text
lietaer-pdf-chapter-region-core
```

Phase 1a and Phase 1 may be developed against pure unit tests and do not require
this profile. The profile is required before Phase 2 acceptance can be claimed
through real-document diagnostics rather than synthetic fixtures.

Full-book checkpoint only after topology projection and structure-aware gates have
focused tests:

```bash
DOCX_AI_STRUCTURE_RECOGNITION_CACHE_ENABLED=0 DOCX_AI_STRUCTURE_RECOVERY_DOCUMENT_MAP_CACHE_ENABLED=0 \
  bash scripts/run-structural-preparation-diagnostic.sh lietaer-pdf-full-benchmark --run-profile-id structural-ai-first-default
```

Do not use full-book reruns as the ordinary debug loop.

## Success Criteria

Minimum success for the new architecture slice:

- Chapter 9 remains present in `DocumentMap` and projected topology.
- Composite heading fragments are grouped under one structural heading unit.
- Page placeholders concatenated with chapter headings are split before markdown.
- Compound TOC entries inside bounded TOC regions become structural TOC units.
- Structural gate reports distinguish raw markdown signals from structure-aware
  pass/fail signals.
- The remaining full-book failures, if any, are bucketed into specific topology
  classes instead of appearing only as generic `unmapped_*` or markdown regex
  failures.
- The chapter-region profile passes its topology assertions without a full-book
  rerun.
- A milestone full-book checkpoint shows `DocumentMap` Chapter 9 retained,
  projected composite headings present, and structure-unit coverage improved for
  the previously unmapped heading fragments.

## Risks

- R1 is a real contract change: downstream consumers must either understand
  topology projection or have a compatibility path.
- If implemented as destructive paragraph rewriting too early, it can destabilize
  paragraph IDs and mapping reports. Prefer sidecar structural units first.
- R2 can hide final-output defects if raw markdown signals are removed too soon.
  Keep markdown signals as advisory diagnostics during migration.
- R3 can break unrelated output-quality tests if text-hygiene functions are
  removed before structural gates stop depending on them.
- R2 without restore/mapping unit aggregation will not materially improve
  `unmapped_source_threshold` for composite heading fragments.
- A sidecar projection that Stage 2 does not see will create a new reconciliation
  conflict class. Stage 2 descriptor plumbing is part of R1, not an optional
  follow-up.
- First-20-only diagnostics do not cover the current late-book failures. A cheap
  chapter-region profile is required to avoid full-book reruns as the inner loop.
- Introducing `split_hints` without bumping the `DocumentMap` cache fingerprint
  would let pre-Phase-3 cached maps act as authority for binding splits even
  though Stage 1 never had the opportunity to emit hints for them. The cache
  bump in Phase 3 mitigates this risk.

## Recommended Decision

Proceed with **R1 first**, but design it as the first step of R1+R2+R3.

Do not start with R2 alone: moving the gate to `StructureMap` without topology
projection would make metrics look better while leaving composite heading
fragments broken in source artifacts.

Do not start with another deterministic composite-heading regex: that repeats the
current whack-a-mole pattern and conflicts with the parent spec's authority
boundary.

The next implementation tasks, in order, should be:

1. Phase 1a: land `DocumentMapSplitHint` schema-only (no projection, no
   binding splits, allow-listed in Stage 1 prompt with empty default).
2. Phase 1: land `DocumentTopologyProjection` / `StructuralUnit` scaffolding,
   artifact writer, retention, and feature flags. No behavior change.
3. Phase 2: implement audited `merge_heading_continuation` for
   DocumentMap-backed chapter heading groups, with Stage 2 descriptor
   propagation and reconciliation coverage by unit.

This ordering is the smallest radical step that changes the architecture instead
of adding one more output cleanup rule, while keeping each slice independently
verifiable.
