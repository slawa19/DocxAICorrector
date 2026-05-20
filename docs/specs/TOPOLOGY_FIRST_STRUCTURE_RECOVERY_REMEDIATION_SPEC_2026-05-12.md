# Topology-First Structure Recovery Remediation Spec

Date: 2026-05-12
Status: Partially implemented; Phase 4 Prerequisite COMPLETE for contracted scope
Parent spec: `docs/AI_FIRST_STRUCTURE_RECOVERY_SPEC_2026-05-08.md`
Related follow-up: `docs/specs/Folloup AI structure recovery.md`
Continuation source of truth: `docs/specs/STRUCTURE_RECOGNITION_COMPLETION_PLAN_2026-05-14.md`

## Implementation Status (as of 2026-05-20)

This addendum is the authoritative landed-status summary for this spec. Read it before referencing any later section to avoid treating proposed wording as implemented behavior.

Landed:

- **R1 Stage 1.5 DocumentMap Topology Projection** \u2014 substantially implemented. `DocumentTopologyProjection` / `StructuralUnit` exist, projection schema is at version 2, `apply_document_map_topology(...)` consumes layout signals, and the closed `unit_type` / `authority` vocabularies are in place.
- **Layout Signal Evidence Slice** (separate spec `docs/specs/LAYOUT_SIGNAL_EVIDENCE_SLICE_SPEC_2026-05-14.md`) \u2014 implemented as an intermediate slice between R1 and the rest of this spec. Layout evidence may confirm but never synthesize Stage 1 authority. `body_font_baseline_outlier`, `font_cluster_match`, `page_break_boundary` are accepted evidence tags; `candidate_page_artifact_split` remains candidate-only.
- **Phase 4 Prerequisite \u2014 Split Fallback Hardening (Slices 1\u20136)** \u2014 IMPLEMENTED and verified by focused tests:\n  - Slice 1 Topology Precedence Guard in `apply_structure_map(...)` (`src/docxaicorrector/structure/recognition.py`), covered by `TestTopologyAuthorityGuard` (13 tests).\n  - Slice 2 Fallback Telemetry via `StructureFallbackStats` (`src/docxaicorrector/core/models.py`).\n  - Slice 3 Bounded Retry \u2014 timeout-only; no temperature / max_tokens changes.\n  - Slice 4 Recursion Cap \u2014 fail-closed semantics.\n  - Slice 5 Topology-Aware Boundary Snapping via `_select_safe_split_boundary` and `_build_protected_split_ranges` (14 boundary tests).\n  - Slice 6 Fallback Metadata Side-Map via `StructureFallbackMetadata` + `fallback_metadata_by_index`. No `ParagraphClassification` schema change.\n- **R2 Structure-Aware Quality Gates** \u2014 materially advanced for `toc_body_concat` and unmapped thresholds (`*_gate_source` fields, structure-unit basis when projection is present), but not a universal gate migration.\n\nNot yet implemented:\n\n- **Slice 7 root window tuning.** Diagnostic / config-only. Gated by the threshold rule: retry-success ratio < 0.3 AND splits >= 3 per document AND capped == 0. Awaiting telemetry data.\n- **R3 Markdown Postprocessor Retirement.** Authority labelling and provenance fields landed on touched late-phase / acceptance / structural-validation surfaces, but `normalize_false_fragment_headings_markdown`, `normalize_list_fragment_regressions_markdown`, `normalize_page_placeholder_heading_concats_markdown`, and `normalize_residual_bullet_glyphs_markdown` still execute in the pipeline. Actual normalizer removal has not started globally.\n- **Full-book milestone evidence.** The latest completed `lietaer-pdf-full-benchmark` run (`20260520T111314Z_1196_Rethinking-money_-How-new-currencies-turn-scarcity-into-prosperity-Bernard-Lietaer-Jacqui-Dunne`) still fails only `formatting_diagnostics_threshold`, `unmapped_source_threshold`, and `unmapped_target_threshold` (`172 / 12`, `172 / 12`, `157 / 6`). `residual_bullet_glyphs_present` now passes at the acceptance layer with gated count `0` while raw remains `25`, and `key_headings_preserved` now passes with `missing = []` and `source_heading_count = 0` under the adopted narrow validator contract. See the continuation plan's section 5.0 Live Failure Inventory for the live inventory and caveats.\n\nExplicitly out of scope for this spec:\n\n- Stage 1 prompt / schema / cache changes (including any \"multi-signal chapter promotion from TOC + body neighborhoods\"). The latest full-book report explicitly preserves Chapter 8, Chapter 10, and Chapter 11 as `chapter_heading` units plus the bounded TOC split; any stronger claim about Chapter 9 (either still missing or already fully promoted) requires a direct file:line citation from the latest run report, per the continuation plan section 1.1 item 10.\n- Index / page-range heading authority class (e.g. entries like `179\u2013180`, `182, 192\u2013193`). Broader recognition redesign for that authority class remains out of scope here and stays on the separate path in `docs/specs/INDEX_REGION_AUTHORITY_SPEC_2026-05-20.md`; the latest milestone confirms only the narrow validator/acceptance slice.\n- Residual bullet glyph root-cause work. Mini-plan A is no longer an active failed-check package in the latest milestone, but the raw residual-glyph observation remains `25`; any deeper root-cause package still belongs outside this spec.\n- Unmapped-fragment tracing in the back matter / index region. Belongs to the continuation plan's mini-plan B and the future index-region spec.\n\nWhen following Slices 1\u20137 below, treat Slices 1\u20136 as historical reference: their proposed wording has been implemented and may differ from the current code shape. Slice 7 wording remains proposal-state.\n\n## Problem Statement

The current `lietaer-pdf-full-benchmark` work has reached diminishing returns. The
latest iterations improved isolated symptoms, but the full-book structural gate
still fails on the same classes:

Historical note: the section immediately below predates the 2026-05-19 status
addendum and is preserved as architectural diagnosis context, not as the live
failure inventory. For current full-book failing checks, priorities, and
allowed next steps, treat `docs/specs/STRUCTURE_RECOGNITION_COMPLETION_PLAN_2026-05-14.md`
section `5.0 Live Failure Inventory` as authoritative.

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
`this page intentionally left blank` followed by `chapter|РіР»Р°РІР°`.

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
  `corpus_registry.toml` covering Chapter 8-11 and the over-merged TOC region.
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

## Phase 4 Prerequisite: Split Fallback Hardening

This section is added 2026-05-13 after diagnosing AI structure-recognition split
fallback behavior on lietaer-pdf-full-benchmark runs. It is a prerequisite to
Phase 4, not part of Phase 4.

### Motivation

`_classify_descriptor_window_with_fallback` in
`src/docxaicorrector/structure/recognition.py` recursively bisects the
descriptor window on AI timeout (current progress text: "уточняю разбиением"). Current
implementation has no retry, no overlap, no recursion cap, and no marking of
classifications produced under fallback. It also does not consult the
`DocumentTopologyProjection` when accepting Stage 2 results inside descriptor
windows whose midpoint falls inside a high-confidence topology unit.

Risks observed:

1. Recursion can split through the middle of a single logical unit (heading +
   first paragraph, compound TOC entry already merged by Stage 1.5), producing
   two halves classified independently and incoherently.
2. A single slow OpenAI response can amplify into many smaller, more expensive
   sub-requests with no upper bound on total cost.
3. Stage 2 results inside fallback halves can override Stage 1.5 anchored
   units of higher confidence (`document_map_outline` / `document_map_toc`,
   `confidence=high`) because no precedence guard is applied in
   `apply_structure_map`.
4. Downstream reconciliation cannot distinguish "AI-confident" from
   "AI-emergency-fallback" results because `ParagraphClassification` carries no
   provenance bit.

### Slices

The remediation is decomposed into seven independently mergeable slices.
Slice 1 is a strict prerequisite for continuing Phase 4 interpretation: it is
an invariant guard, not a Phase 4 feature. Slices 2-7 may be reordered when
structural diagnostic data shows a better sequence, but behavior-changing
slices must not be driven by repeated full-book quality-gate loops.

#### Slice 1: Topology Precedence Guard (Prerequisite)

**Status:** Required before Phase 4. Smallest viable change. No flag.

**Integration point (locked):** `apply_structure_map(...)` in
`src/docxaicorrector/structure/recognition.py`. The function already accepts
`document_map` and tracks `anchor_conflicts_deferred`; Slice 1 extends the
same pattern with `topology_projection` and local counters. Do not move this
logic into `reconciliation.py` for Slice 1.

**Signature change:**

```python
def apply_structure_map(
    paragraphs,
    structure_map,
    *,
    min_confidence="medium",
    document_map=None,
    topology_projection=None,
) -> dict[str, int]:
    ...
```

**New counters in return dict:**

- `topology_authority_conflicts_deferred`
- `topology_authority_protected_count`

**Guard activation conditions.** Guard applies to `logical_index` only when ALL
of the following hold:

- `topology_projection is not None`
- `unit = topology_projection.get_unit(logical_index)` is not None
- `unit.confidence == "high"`
- `unit.authority in {"document_map_outline", "document_map_toc"}`
- `unit.unit_type in {"toc_entry", "chapter_heading", "section_heading"}`

When the guard is inactive, behavior is unchanged from current
`apply_structure_map`. `document_map_anchor`, `document_map_split_hint`,
review-zone, low-confidence, and non-document-map authorities are explicitly
out of scope for Slice 1.

**Conflict table.** When the guard is active, Stage 2 classification is
evaluated against `unit.unit_type`:

| `unit.unit_type` | Stage 2 classification | Outcome |
| --- | --- | --- |
| `chapter_heading` | `heading` with `heading_level == unit.heading_level` | concord - apply |
| `chapter_heading` | `heading` with missing or different `heading_level` | conflict - defer |
| `chapter_heading` | `body` / `toc_entry` / other supported role | conflict - defer |
| `section_heading` | `heading` with `heading_level == unit.heading_level` | concord - apply |
| `section_heading` | `heading` with missing or different `heading_level` | conflict - defer |
| `section_heading` | `body` / `toc_entry` / other supported role | conflict - defer |
| `toc_entry` | `toc_entry` if Stage 2 supports that role | concord - apply |
| `toc_entry` | `heading` / `body` / any non-TOC role | conflict - defer |

If Stage 2 does not currently support `toc_entry` as a classification role,
the concord row for `toc_entry` is a forward-compatible rule; current behavior
should still treat `heading` and `body` as conflicts for topology TOC units.

**Heading-level precondition.** The conflict table above assumes both the
topology unit (`TopologyUnit` / `StructuralUnit`) and the Stage 2
classification carry a comparable `heading_level`. If either side does not yet
carry this field, Slice 1 must extend the topology-side dataclass (not
`ParagraphClassification`) with `heading_level: int | None = None`, populate
it from `DocumentMap` outline level during Stage 1.5 projection, and treat
`heading_level is None` on the topology unit as "unknown" - in that case
`heading` of any level is concord, only role mismatch is conflict. This
adjustment is in scope for Slice 1 only when needed; otherwise it stays out
of scope.

Concord increments `topology_authority_protected_count` per applied paragraph.
Conflict increments `topology_authority_conflicts_deferred` and skips applying
that Stage 2 result. "Defer" means do not mutate the paragraph role,
`structural_role`, `heading_source`, or `heading_level` from the conflicting
classification. Existing role state and later reconciliation remain responsible
for the final output.

**Non-goals for Slice 1:**

- No flag gating. The guard is unconditional once `topology_projection` is
  provided by the caller.
- No schema bump on `ParagraphClassification` or `StructureMap`.
- No changes to fallback/retry/cap/overlap in
  `_classify_descriptor_window_with_fallback`.
- No cache fingerprint changes.
- No full-book quality-gate rerun in Slice 1.
- No new event names; expose counters through the existing summary/metrics path.

**Caller updates.** Every call site of `apply_structure_map(...)` must pass
`topology_projection=` when the caller has it. The expected production call site
is `_run_structure_recognition(...)` in `src/docxaicorrector/processing/preparation.py`,
which already has `topology_projection`. Tests/callers without topology context
pass `topology_projection=None` or omit the kwarg for unchanged behavior.

The implementation agent must search call sites with repository search tooling,
not by assumption, and update each call site explicitly.

**Tests.** Add focused tests in `tests/test_structure_recognition.py`. Cover at
minimum:

- guard inactive when `topology_projection is None`;
- guard inactive when unit confidence is not high;
- guard inactive when authority is not `document_map_outline` /
  `document_map_toc`;
- guard inactive when unit type is `body` / `page_artifact` / unknown;
- concord for `chapter_heading` with matching heading level;
- conflict for `chapter_heading` with `body`;
- conflict for `chapter_heading` with wrong heading level;
- concord for `section_heading` with matching heading level;
- conflict for `section_heading` with wrong heading level;
- conflict for `toc_entry` with `heading`;
- conflict for `toc_entry` with `body`;
- counters propagate into the return dict;
- uncovered paragraphs still accept Stage 2 classification as before.

#### Slice 2: Split Fallback Telemetry And Honest Progress

Make split fallback observable before changing its behavior. Add aggregate
fallback stats without changing the AI response schema:

- `structure_window_split_count`
- `structure_max_fallback_depth`
- `structure_split_fallback_descriptor_count`
- `structure_timeout_retry_count` (initially zero until Slice 3)
- `structure_timeout_retry_succeeded_count` (initially zero until Slice 3)
- `structure_timeout_retry_failed_count` (initially zero until Slice 3)
- `structure_split_fallback_capped_descriptor_count` (initially zero until Slice 4)

Prefer an internal stats object over tuple-return sprawl, for example:

```python
@dataclass
class StructureFallbackStats:
    split_count: int = 0
    max_fallback_depth: int = 0
    split_fallback_descriptor_count: int = 0
    timeout_retry_count: int = 0
    timeout_retry_succeeded_count: int = 0
    timeout_retry_failed_count: int = 0
    capped_fallback_descriptor_count: int = 0
```

Store stats on `StructureMap` or pass them through the existing summary path;
do not add fields to `ParagraphClassification` in this slice. Persist aggregate
fields into `preparation_diagnostic_snapshot` so full-book evidence can be
correlated with split density.

Replace optimistic progress wording such as "refining by splitting" with a
neutral timeout message, e.g.:

```text
AI timeout on a large structure window; retrying with smaller windows.
```

If the progress event has `current_window`, `total_windows`, `descriptor_count`,
and `fallback_depth`, include them in metrics and logs. Do not rely on parsing
human-readable progress text for diagnostics.

#### Slice 3: Bounded Retry Before Split

Before splitting a window on a timeout-like exception, retry the same window at
most once with a bounded extended timeout. Retry must not silently exceed the
stage budget.

Required controls:

- `structure_recognition_timeout_retry_multiplier` (proposed default: `1.5`)
- `structure_recognition_timeout_retry_max_seconds`
- future-compatible check for remaining stage budget when such a budget exists

Retry should change only timeout unless the provider/runtime already has a
safe, supported deterministic request parameter. Do not add provider-specific
fields such as temperature in this slice. Do not lower `max_tokens` for retry;
that can truncate classification output and convert timeouts into parse errors.

Telemetry from Slice 2 must distinguish:

- retry attempted;
- retry succeeded and avoided split;
- retry failed and proceeded to split.

High retry-success rate indicates transient latency and argues against reducing
root window size. Low retry-success rate with frequent splits indicates root
windows/token targets are too aggressive.

#### Slice 4: Recursion Cap With Fail-Closed Semantics

Add a hard cap on recursion depth and total fallback expansions per Stage 2 run
(proposed defaults: max depth `3`, max expansions `8`). Cap values are
configuration settings, not feature flags.

When the cap is reached, do not synthesize `body/low` classifications for
uncovered descriptors. "No classification" is preferable: default downstream
behavior is already body-like, and synthetic low-confidence classifications
pollute Phase 4 accounting.

Covered descriptors may receive a deterministic capped fallback only when all
of these hold:

- the descriptor is covered by high-confidence topology authority protected by
  Slice 1;
- the fallback preserves that authority rather than inventing a new role;
- the fallback is marked in side metadata/stats as capped.

Otherwise the window is treated as failed/degraded for those descriptors, and
the snapshot records the cap. This is fail-closed: it must not create new
authoritative structure from timeout recovery.

#### Slice 5: Topology-Aware Split Boundary And Optional Overlap

Internal fallback split must not cut through a high-confidence topology unit.
When choosing the midpoint, snap the split boundary to the nearest safe topology
unit boundary when possible.

Rules:

- Build candidate protected ranges from high-confidence topology units with
  `authority in {"document_map_outline", "document_map_toc"}` and more than one
  logical index.
- If the midpoint falls inside such a range, choose the nearest boundary outside
  that unit that leaves both left and right windows non-empty.
- If no safe non-empty boundary exists, do not recurse blindly. Let Slice 4 cap
  or the window-failed path handle the case.
- Guard against pathological cases where snapping returns the same split point
  repeatedly.

**Boundary-selection invariants (mandatory):**

- progress: for the chosen boundary, `len(left) >= 1` and `len(right) >= 1`
  and `len(left) + len(right) == len(window)`;
- non-regression: the chosen split point is strictly different from any
  ancestor split point on the current recursion path (no fixed-point loop);
- determinism: boundary selection must be deterministic for a given
  `(window, topology_projection)` pair - no dependency on hash ordering or
  iteration nondeterminism;
- tie-break: when two adjacent protected units are equally close to the
  midpoint, prefer the boundary that leaves the larger protected unit intact;
  on full tie, prefer the boundary to the left of the midpoint;
- coverage: if both left-snap and right-snap produce empty halves, mark the
  window unsplittable and fall through to Slice 4 cap rather than emitting an
  empty recursion frame.

Descriptor overlap around the final split point is optional and lower priority
than boundary snapping. If implemented, it must be bounded (for example 2-20
descriptors), must not defeat recursion caps, and must rely on existing
`_merge_window_classifications(...)` edge-distance behavior for duplicate
classification resolution.

This is lower token/API cost than broad overlap, but it is not "free": tests
must cover non-empty windows, repeated split prevention, and multi-index units
near document boundaries.

#### Slice 6: Fallback Provenance Without AI Schema Bump

Do not add `fallback_origin`, `evidence`, or `fallback_depth` to
`ParagraphClassification` in this remediation sequence. That would change the
classification schema/cache contract and may invalidate full-book caches.

Instead, keep provenance outside the AI response object:

```python
@dataclass(frozen=True)
class StructureFallbackMetadata:
    fallback_depth: int = 0
    capped: bool = False
    source: str = "primary"  # primary | retry | split_fallback | cap_reached

@dataclass
class StructureMap:
    ...
    fallback_metadata_by_index: dict[int, StructureFallbackMetadata] = field(default_factory=dict)
```

If split fallback classifications are accepted, confidence demotion may mutate
the existing `confidence` value before insertion into `StructureMap`:

- `high -> medium`
- `medium -> low`
- `low -> low`

Do not demote high-confidence `document_map_reconciliation` patches or any
deterministic topology-preserving fallback from Slice 4. Phase 4 metrics must be
able to report how many units depended on split fallback metadata.

#### Slice 7: Root Window Tuning From Diagnostics

Tune root window size and token targets only after Slices 2-3 expose retry and
split telemetry. The main decision signal is not `window_split_count` alone:

- high `structure_timeout_retry_succeeded_count` means provider latency is
  transient; do not reduce root window size solely because split was attempted;
- low retry success with frequent splits means root windows or
  `structure_recovery_anchored_classification_target_input_tokens` are too
  aggressive for the current provider/timeout;
- frequent capped fallbacks mean retry/split tuning is still unsafe and should
  not be hidden by threshold relaxation.

**Threshold rule (operational).** A root-window reduction is justified only
when ALL of the following hold over a representative run (full-book or
chapter-region with the same provider/profile as the failing scenario):

- `structure_window_split_count >= 3` (splits are not a one-off);
- `structure_timeout_retry_count >= 3` (retry telemetry is statistically
  meaningful, not based on a single sample);
- `structure_timeout_retry_succeeded_count / structure_timeout_retry_count
  < 0.3` (retry is NOT rescuing most timeouts, so latency is not transient);
- `structure_split_fallback_capped_descriptor_count == 0` (caps are not
  masking a deeper problem; if non-zero, fix retry/split first).

When the rule fires, perform exactly one config-only commit that reduces
`structure_recovery_anchored_classification_target_input_tokens` by 15-25%
(no other config changes, no logic changes). Then re-measure on the same
profile. Do not stack reductions; iterate at most once per measurement
cycle. If after the reduction `structure_window_split_count` is unchanged,
the bottleneck is not window size and Slice 7 stops there - escalate to
provider/timeout review instead of further token cuts.

Any root-window tuning is a separate configuration change with focused
diagnostics. Do not use full-book quality-gate reruns as the ordinary tuning
loop.

### Slice 1 Verification (Canonical)

Worktree must be free of whitespace errors before any Slice 1 commit:

```bash
git status --porcelain
git diff --check
```

If `git diff --check` reports issues, the agent stops and reports cleanup
needed. Whitespace cleanup is not mixed with this logic slice. Do not use
destructive checkout/reset commands to clean unrelated files unless the user
explicitly requests it.

Then run focused canonical checks:

```bash
echo START; wsl.exe -d Debian bash -c "cd /mnt/d/www/projects/2025/DocxAICorrector && bash scripts/test.sh tests/test_structure_recognition.py -q 2>&1"; echo DONE
echo START; wsl.exe -d Debian bash -c "cd /mnt/d/www/projects/2025/DocxAICorrector && bash scripts/test.sh tests/test_structure_topology.py -q 2>&1"; echo DONE
echo START; wsl.exe -d Debian bash -c "cd /mnt/d/www/projects/2025/DocxAICorrector && bash scripts/test.sh tests/test_structure_reconciliation.py -q 2>&1"; echo DONE
```

No full-book quality-gate run in Slice 1.

### Decision Rule for Slicing Order

Slice 1 must land first. Slice 2 should normally land next because it gives the
team structural fallback visibility without changing behavior. Slices 3-7 are
then ordered by structural diagnostic data. This decision must be made from a
structural diagnostic snapshot or focused structure-recognition tests, not from
repeated full quality-gate reruns.
