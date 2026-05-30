# AI-First Structure Recovery Spec

Date: 2026-05-08
Status: Archived 2026-05-30; dead-end / superseded by reader-first migration
Supersedes: `docs/PDF_SEMANTIC_STRUCTURE_RECOVERY_SPEC_2026-05-08.md`

## Problem

The current structure recovery pipeline accumulates heuristics in four modules
(`document/boundaries.py`, `document/layout_cleanup.py`, `document/structure_repair.py`,
`document/relations.py`) and a single AI classifier in `structure/recognition.py`.
Each new difficult document forces another heuristic rule, another test, and a new
edge case. The Lietaer PDF and the End Times PDF demonstrate the limit:

- the AI classifier in `build_structure_map(...)` (see `src/docxaicorrector/structure/recognition.py:210`)
  receives sliding windows of up to `max_window_paragraphs = 1800` paragraphs
  with `overlap_paragraphs = 50` and a per-paragraph preview limited to
  `_DESCRIPTOR_PREVIEW_CHARS = 600` characters plus only one `prev` and one `next`
  neighbour;
- this means the model never sees a global view of the document — it cannot
  reconcile a TOC found at paragraph 80 with a chapter heading found at
  paragraph 1500;
- the heuristic layers run **before** the AI and already mutate roles,
  delete paragraphs, and merge boundaries, so the AI is constrained to
  whatever decisions heuristics have already made;
- failures are global in nature (front matter end, TOC region, chapter outline,
  level hierarchy) but the AI is only given a local, paragraph-level
  classification task.

The architectural problem is not the AI quality. It is that the AI is given a
narrow local task while the failures are global structural failures.

This specification replaces the heuristic-first, AI-as-classifier architecture
with an AI-first architecture in which the AI builds a single
`DocumentMap` of the whole document, and all downstream classification and
deterministic post-processing project from that map.

## Goals

1. Make the AI the primary reasoner about document structure.
2. Give the AI a global view of the document in a single reasoning pass before
   any per-paragraph classification happens.
3. Reduce heuristic code in `document/structure_repair.py` and
   `document/layout_cleanup.py` to **signal extraction only**; remove their
   ability to mutate roles, delete paragraphs, or merge boundaries.
4. Stabilize PDF front matter / TOC / chapter recovery without writing new
   document-specific heuristics.
5. Keep the existing readiness contract (`ready` / `ready_with_warnings` /
   `blocked_needs_structure_repair` / `blocked_unsafe_best_effort_only`) as
   the publication gate, exactly as today in
   `src/docxaicorrector/structure/validation.py:210`.
6. Make every AI decision auditable through saved artifacts and reproducible
   through a deterministic cache.
7. Make the new pipeline a feature-flagged opt-in path that can be disabled
   without redeploy.

## Non-Goals

- No new boundary normalization rules.
- No new PDF extraction backend in this slice.
- No OCR redesign.
- No new UI flow; the change is strictly a preparation-phase change.
- No replacement of the existing windowed AI classifier on the legacy path —
  the new path runs alongside it, gated by config.
- No expansion of the role taxonomy beyond the current
  `_VALID_AI_ROLES` set in `src/docxaicorrector/structure/recognition.py:25`.

## Current State (verified in code)

### Pipeline order

Verified against
`src/docxaicorrector/document/extraction.py:extract_document_content_with_normalization_reports`
and `src/docxaicorrector/processing/preparation.py:_prepare_document_for_processing`.

Inside `extract_document_content_with_normalization_reports`:

1. extraction of raw blocks (`document/extraction.py:_build_raw_document_blocks`)
2. paragraph boundary normalization (`document/boundaries.py:_normalize_paragraph_boundaries`)
3. logical paragraph unit construction (`document/extraction.py:_build_logical_paragraph_units`)
4. inline break normalization (`document/extraction.py:_normalize_inline_break_paragraphs`)
5. short standalone heading promotion (`document/roles.py:promote_short_standalone_headings`)
6. front-matter display-title normalization
   (`document/roles.py:normalize_front_matter_display_title`)
7. layout artifact cleanup (`document/layout_cleanup.py:clean_paragraph_layout_artifacts`)
8. PDF structure repair (`document/structure_repair.py:repair_pdf_derived_structure`)
9. paragraph identity reassignment (`_reassign_paragraph_identities`)
10. paragraph relation building (`document/relations.py:build_paragraph_relations` +
    `apply_relation_side_effects`)

Later, inside `_prepare_document_for_processing`:

11. structural validation (`structure/validation.py:validate_structure_quality`)
12. AI structure recognition (`structure/recognition.py:build_structure_map`,
    then `apply_structure_map`)
13. segment detection (`document/segments.py:detect_document_segments`)

Steps 5 and 6 (`promote_short_standalone_headings`,
`normalize_front_matter_display_title`) currently mutate
`ParagraphUnit.role` and `ParagraphUnit.heading_*` and are therefore in scope
for the Stage 0 contract change in Slice 1, alongside `structure_repair.py`
and `layout_cleanup.py`.

Additional verified constraints that affect implementation:

- `_build_raw_paragraph(...)` in `document/extraction.py` already assigns
  heuristic structural fields before Stage 0 helpers run: `heading_level`,
  `heading_source = "heuristic"`, `role = classify_paragraph_role(...)`, and
  `role_confidence` are set around
  `src/docxaicorrector/document/extraction.py:389-414`. AI-first mode must
  either suppress non-explicit extraction-time role decisions or copy them into
  advisory hint fields before resetting mutable structural fields.
- `structure/recognition.py:apply_structure_map(...)` skips paragraphs whose
  `role_confidence` is `explicit` or `adjacent`, so AI-first mode must define
  which pre-existing role decisions are authoritative and which are only
  advisory.
- Current Stage 3 policy is narrower than that original concern: ordinary
  Stage 2 AI classifications still cannot override `explicit` / `adjacent`
  paragraphs, but audited `document_map_reconciliation` patches may override
  them when the same paragraph also has a matching high-confidence Stage 1
  anchor and the paragraph is not an asset/caption surface.
- Front-matter pre-body `body` classifications are now split: matching
  medium/high `body` anchors become `front_matter_body_advisories`, while
  `front_matter_leaks` remains reserved for true pre-body structural conflicts.
- Reconciliation artifacts should be consumed via `patched_logical_indexes`.
  `patched_source_indexes` is no longer part of the supported report/payload
  contract.
- `_split_compound_toc_aligned_paragraphs(...)` and
  `_split_toc_aligned_compound_paragraph(...)` in
  `document/structure_repair.py` can create multiple `ParagraphUnit` objects
  from a single original paragraph. The clone helpers inherit the original
  `source_index`, so `source_index` is not a safe unique key for Stage 1
  anchors, Stage 2 classifications, or Stage 3 reconciliation.
- `StructureMap.classifications` is keyed by a single `int`, and
  `apply_structure_map(...)` looks up classifications by `paragraph.source_index`.
  Duplicate `source_index` values therefore collapse distinct paragraphs onto
  one classification.
- `build_layout_cleanup_status_note(...)` in `processing/preparation.py` renders
  `LayoutArtifactCleanupReport.removed_*` fields as user-facing "removed"
  counts. AI-first mode must not reinterpret those fields as "flagged" counts
  without a discriminator and mode-aware UI/status text.

### Data the AI currently sees

`ParagraphDescriptor.to_prompt_dict(...)` in
`src/docxaicorrector/core/models.py:251` exposes per paragraph:

`i`, `t` (≤600 chars), `len`, `s` (style name), `b` (bold), `ctr` (centered),
`caps` (all caps), `pt` (font size in pt), `num` (has numbering), `hl`
(explicit heading level), `prev` (≤600 chars), `next` (≤600 chars), `iso`
(isolated marker), `toc` (toc candidate), `scr` (scripture reference).

The model is asked to return per paragraph: `{"i", "r", "l", "c"}` —
role, heading level, confidence (`high|medium|low`).

### Configuration keys today

From `config.toml`:

- `[models.structure_recognition].default` is optional; when omitted it inherits `[models.text].default`
- `[structure_recognition] mode | max_window_paragraphs | overlap_paragraphs |
  timeout_seconds | min_confidence | cache_enabled | save_debug_artifacts`
- `[structure_validation] enabled | min_paragraphs_for_auto_gate | …`
- `[paragraph_boundary_normalization] enabled | mode | save_debug_artifacts`
- `[layout_artifact_cleanup] enabled | min_repeat_count | …`
- `[relation_normalization] enabled | profile | enabled_relation_kinds | …`

### Artifacts written today

- `.run/structure_maps/<cache_key>.json`
- `.run/structure_validation/<timestamp>.json`
- `.run/layout_cleanup_reports/<source_hash>.json`
- `.run/paragraph_boundary_reports/<source_hash>.json`
- `.run/relation_normalization_reports/<source_hash>.json`

These contracts are preserved.

## Decision Summary

Adopt a three-stage AI-first structure recovery pipeline:

- **Slice 0 prerequisite — Plumbing and coordinates**: introduce the config
  plumbing, mode propagation, legacy parity tests, and stable paragraph
  coordinate needed before any behaviour-changing Stage 0 work begins.
- **Stage 0 — Signals**: extraction and pre-AI modules expose signals on
  `ParagraphUnit`. They no longer mutate roles, no longer delete paragraphs,
  no longer merge boundaries on their own decisions.
- **Stage 1 — Document Map**: a single AI call receives a compact descriptor
  for **every** paragraph of the document and returns a
  `DocumentMap` describing front-matter end, TOC region, full outline, and
  review zones. This is the global reasoning pass.
- **Stage 2 — Anchored Classification**: the existing windowed AI classifier
  is reused, but each descriptor carries the `DocumentMap` anchor for that
  paragraph, and the system prompt is changed to enforce anchor consistency.
- **Stage 3 — Reconciliation**: a deterministic check verifies that every
  outline entry from Stage 1 has a matching heading from Stage 2. If
  divergence exceeds a budget, a single targeted AI call is allowed to
  reclassify a small, bounded set of paragraphs.

The publication gating from `validate_structure_quality(...)` runs after
Stage 3 and remains the single readiness contract. The current pre-AI
validation call is retained only as a diagnostic/escalation gate; it no longer
serves as the final publication readiness proof for the AI-first path.

### Slice 0 prerequisite — Plumbing and stable coordinates

This prerequisite slice is mandatory before Stage 0 implementation. It makes
the feature flag and rollback claims true without changing legacy behaviour.

Required changes:

1. Add full config plumbing for `[structure_recovery]` and nested sections in
   `core/config.py` and `core/config_structure_sections.py`, including defaults,
   env overrides, clamps, and tests. The resolved `app_config` keys must be
   flat and explicit, matching the existing configuration style.
2. Propagate `structure_recovery_enabled` / `structure_recovery_mode` into
   `extract_document_content_with_normalization_reports(...)` through the
   existing `app_config` path. No document helper may infer AI-first mode from
   global state.
3. Add a final-topology paragraph coordinate on `ParagraphUnit`, named
  `logical_index`, assigned after the final legacy-compatible paragraph
  topology operation and before any Stage 1/2/3 artifact is built. Stage 1
  `DocumentMap`, Stage 2 `StructureMap`, and Stage 3 reconciliation use this
  coordinate on the current extracted paragraph list. `source_index` remains
  as provenance only.
4. Update cache keys for prepared documents, structure maps, document maps, and
   reconciliation reports to include the structure recovery mode and coordinate
   schema version.
5. Add disabled-mode parity tests proving that
   `structure_recovery.enabled = false` keeps the legacy extraction,
   recognition, validation, and user-facing cleanup-status behaviour unchanged.
6. Keep Stage 0 helper behaviour in legacy mutation/removal mode until
   AI-first mode is explicitly enabled.

This slice intentionally does not introduce `DocumentMap` calls or change
classification behaviour. Its success criterion is safe opt-in plumbing.

## Architecture

### Stage 0 — Signals only

Affected modules (verified mutation surfaces today):

- `document/extraction.py` — already populates the structural fields
  (`paragraph_alignment`, `font_size_pt`, `is_bold`, `style_name`,
  `explicit_heading_level`) and currently also assigns heuristic roles and
  heading fields inside `_build_raw_paragraph(...)`. In AI-first mode,
  non-explicit role/heading decisions from extraction are advisory hints, not
  binding structural state.
- `document/roles.py` — currently mutates roles in
  `promote_short_standalone_headings(...)` and
  `normalize_front_matter_display_title(...)`.
- `document/layout_cleanup.py` — currently **deletes** paragraphs from the
  list inside `clean_paragraph_layout_artifacts(...)`
  (returns a filtered `cleaned` list, see
  `src/docxaicorrector/document/layout_cleanup.py:114–171`).
- `document/structure_repair.py` — currently mutates `role`,
  `structural_role`, `heading_level`, `heading_source` in multiple branches
  (TOC-aligned heading promotion, list-fragment merging, TOC region
  enforcement) and changes paragraph topology through compound TOC splitting.
  Verified at `src/docxaicorrector/document/structure_repair.py:97–100,
  221–248, 267–275, 309–404`.
- `document/relations.py` — `apply_relation_side_effects(...)` mutates only
  `ParagraphUnit.attached_to_asset_id`; it does **not** change roles. This
  module is therefore already compliant with the Stage 0 contract for role
  fields and only needs minor adjustments (the TOC-region detection in
  `relations.py` returns relation objects without mutating roles).

New rules in this stage:

1. In AI-first mode, no Stage 0 helper is allowed to assign or change
   `ParagraphUnit.role`, `structural_role`, `heading_level`, or
   `heading_source`, except for preserving explicit DOCX heading metadata as
   authoritative input.
2. In AI-first mode, no Stage 0 helper is allowed to delete paragraphs from the
   paragraph list.
3. No module is allowed to merge paragraph boundaries based on its own
   structural decision. Boundary normalization (`boundaries.py`) is allowed
   to merge only at the existing `mode = "high_only"` confidence level
   defined in `config.toml`, and the result remains tracked through the
   existing `boundary_source` / `boundary_confidence` /
   `origin_raw_indexes` fields on `ParagraphUnit`; it does not change role.
4. `clean_paragraph_layout_artifacts(...)` runs in one of two explicit modes:
   legacy remove mode keeps the current filtering behaviour; AI-first signal
   mode returns the original list with new flag fields populated.
   `LayoutArtifactCleanupReport` gets a discriminator such as `cleanup_mode`
   and separate `flagged_*` counters. Existing `removed_*` counters continue to
   mean physically removed paragraphs only.
5. `repair_pdf_derived_structure(...)` no longer mutates role fields. Its
   detection branches (TOC-aligned candidates, isolated markers, compound
   TOC paragraphs) produce flags. Compound TOC splitting is not allowed in
   AI-first signal mode before `logical_index` assignment; it is either kept in
   legacy mode or represented as advisory split hints for later AI-guided
   handling. Merging of orphaned bullet glyphs is retained only if it is
   explicitly classified as a boundary repair that occurs before
   `logical_index` assignment and remains tracked through `origin_raw_indexes`.
   The role-promotion branch at `structure_repair.py:97–100` is removed in
   AI-first mode.
6. `promote_short_standalone_headings(...)` and
   `normalize_front_matter_display_title(...)` either become no-ops behind a
   feature flag (`structure_recovery.legacy_role_heuristics_enabled`,
   default `false` when `structure_recovery.enabled = true`) or are
   rewritten to set `heuristic_role_hint` / `heuristic_heading_level_hint`
   without mutating `role`/`heading_level`.
7. Heuristic results become **signals attached to `ParagraphUnit`**.
8. `source_index` is provenance, not identity. Stage 1/2/3 artifacts and
   caches use `logical_index` once Slice 0 is complete.

New `ParagraphUnit` signal fields (added in
`src/docxaicorrector/core/models.py:179`):

```
font_size_z_score: float | None         # standardized vs document median
style_cluster_id: int | None            # k-means over (style_name, font_size_pt, is_bold, is_italic, alignment)
position_fraction: float | None         # 0.0..1.0 in non-empty paragraph order
page_number: int | None                 # if recoverable from extraction
vertical_gap_before_pt: float | None    # if recoverable from PDF flow
is_repeated_across_pages: bool          # set by layout_cleanup, not deleted
is_likely_page_number: bool             # set by layout_cleanup, not deleted
is_isolated_marker: bool                # set by structure_repair, not merged
toc_pattern_hint: bool                  # dot-leader/page-number tail hint
scripture_reference_hint: bool          # already computed by recognition.py, lifted here
boundary_normalization_applied: bool    # already implied; promoted to first-class flag
heuristic_role_hint: str | None         # advisory output of legacy heuristics, never mutates role
heuristic_heading_level_hint: int | None
logical_index: int                      # dense final-topology coordinate for Stage 1/2/3
```

No name collisions exist with the current `ParagraphUnit` fields verified at
`src/docxaicorrector/core/models.py:179` (the existing 32 fields cover
`text`, `role`, `asset_id`, `attached_to_asset_id`,
`paragraph_properties_xml`, `paragraph_alignment`, `heading_level`,
`heading_source`, list-related fields, `paragraph_id`, `source_index`,
`structural_role`, `role_confidence`, `style_name`, `is_bold`, `is_italic`,
`font_size_pt`, `origin_raw_indexes`, `origin_raw_texts`, `layout_origin`,
`boundary_source`, `boundary_confidence`, `boundary_rationale`,
`segment_id`, `segment_level`, `segment_boundary_before`).

These signals are advisory inputs to Stage 1. They never decide a role.

Removed behaviour (verified mutation sites today):

- `repair_pdf_derived_structure(...)` keeps detection logic, but the
   role-mutation branches (TOC-title heading promotion at
   `structure_repair.py:97–100`, TOC-region role enforcement at
   `structure_repair.py:267–275`, list-fragment role override at
   `structure_repair.py:221–248`, and clone/split role assignment in the
   compound TOC path at `structure_repair.py:309–404`) are removed from
   AI-first signal mode. Detection results become signals on `ParagraphUnit`.
   Boundary-level merging of isolated bullet glyphs into the next paragraph is
   retained only before `logical_index` assignment, because it is a merge of
   physically broken paragraphs rather than a structural role decision;
   `origin_raw_indexes` continues to track this.
- `clean_paragraph_layout_artifacts(...)` no longer removes page numbers
   and repeated furniture from the paragraph list. It sets
   `is_repeated_across_pages` and `is_likely_page_number` flags. Removal
   happens during final rendering, after the AI has classified the document.
   New `LayoutArtifactCleanupReport.flagged_*` counters describe flagged
   paragraphs; the existing `removed_*` counters remain literal removals.
   User-facing status text must branch on `cleanup_mode` so it never says
   "removed" for signal-only flags.
- `apply_relation_side_effects(...)` is unchanged: it only mutates
  `attached_to_asset_id`, which does not affect structural classification.

This change is the most invasive part of the spec and is the precondition for
all later stages. It is intentionally aggressive because the goal of the spec
is to stop accumulating heuristic rules.

### Stage 1 — Document Map

New module: `src/docxaicorrector/structure/document_map.py`.

Public function:

```
def build_document_map(
    paragraphs: list[ParagraphUnit],
    *,
    client: object,
    model: str,
    timeout: float,
    max_input_paragraphs: int,
    progress_callback: DocumentMapProgressCallback | None = None,
) -> DocumentMap
```

New dataclasses (added next to existing models in `core/models.py`):

```
@dataclass(frozen=True)
class DocumentMapOutlineEntry:
    title: str
    level: int                       # 1..6
    logical_index: int               # ParagraphUnit.logical_index of the heading in the body
    confidence: str                  # high|medium|low
    evidence: tuple[str, ...]        # e.g. ("style_cluster=2","matches_toc_entry=12","gap_before")

@dataclass(frozen=True)
class DocumentMapTocEntry:
    title: str
    target_level: int                # 1..6
    candidate_body_logical_index: int | None
    confidence: str

@dataclass(frozen=True)
class DocumentMapTocRegion:
    start_logical_index: int
    end_logical_index: int
    header_logical_index: int | None
    entries: tuple[DocumentMapTocEntry, ...]
    confidence: str

@dataclass(frozen=True)
class DocumentMapReviewZone:
    start_logical_index: int
    end_logical_index: int
    reason: str                      # e.g. "ambiguous_front_matter"
    severity: str                    # info|warning|critical

@dataclass(frozen=True)
class DocumentMap:
    body_start_logical_index: int
    toc_region: DocumentMapTocRegion | None
    outline: tuple[DocumentMapOutlineEntry, ...]
    paragraph_anchors: dict[int, "DocumentMapAnchor"]
    review_zones: tuple[DocumentMapReviewZone, ...]
    model_used: str
    total_tokens_used: int
    processing_time_seconds: float
    sampled: bool                    # True if hierarchical sampling was applied
    sampled_logical_indexes: tuple[int, ...]

@dataclass(frozen=True)
class DocumentMapAnchor:
    role: str                        # one of _VALID_AI_ROLES
    heading_level: int | None
    confidence: str
```

#### Per-paragraph descriptor for Stage 1

Stage 1 uses a **shorter** descriptor than Stage 2, because the goal is
to fit the whole document into a single context. Maximum size per paragraph
is intentionally tight:

```
{
  "i": <logical_index>,
  "t": <text preview, max 120 chars>,
  "len": <full text length>,
  "sty": <style_cluster_id or null>,
  "b": <is_bold>,
  "ctr": <is_centered>,
  "caps": <is_all_caps>,
  "sz": <font_size_z_score rounded to 0.1, or null>,
  "pg": <page_number or null>,
  "pos": <position_fraction rounded to 0.001>,
  "gap": <vertical_gap_before_pt rounded to 0.5, or null>,
  "rep": <is_repeated_across_pages>,
  "pn":  <is_likely_page_number>,
  "iso": <is_isolated_marker>,
  "toc": <toc_pattern_hint>,
  "scr": <scripture_reference_hint>,
  "hl":  <explicit_heading_level or null>
}
```

The original full text is **not** sent in Stage 1. The 120-char preview is
sufficient for outline reasoning because the document is structurally
characterized by short cues (titles, TOC entries, chapter starts) rather than
full body prose.

#### Hierarchical sampling

If `len(paragraphs) > max_input_paragraphs` (default `max_input_paragraphs = 6000`),
Stage 1 selects a structural sample:

1. Always include every paragraph that satisfies any of:
   - `is_bold`, `is_centered`, `is_all_caps`,
   - `style_cluster_id != default_cluster`,
   - `vertical_gap_before_pt` above the document p90 gap,
   - `toc_pattern_hint`, `is_isolated_marker`, `scripture_reference_hint`,
   - `len < 60` characters,
   - `explicit_heading_level is not None`.
2. Plus uniform anchor samples from remaining paragraphs at a density that
   fits the budget.
3. The descriptors include the final-topology `logical_index` so the model
  reasons in the same coordinate system used by Stage 2 and Stage 3.

The set of sampled indexes is recorded in `DocumentMap.sampled_logical_indexes`.
Anchors for non-sampled paragraphs default to
`DocumentMapAnchor(role="body", heading_level=None, confidence="low")`.

#### Stage 1 prompt

A new prompt file: `prompts/document_map_system.txt`.

System prompt structure (final wording is implementation-time; the contract is
the schema and the obligations):

- Task: "You are a senior book editor. You receive a structural skeleton of a
  document. Build a global map of its structure. You must reason globally
  about front matter end, table of contents, chapter outline, and level
  hierarchy."
- Inputs explained: descriptor schema above.
- Required obligations:
   1. Identify `body_start_logical_index`.
  2. If a table of contents is present, return its bounded region with
     entries; if absent, return `null`.
  3. Build a complete outline of body sections; every TOC entry that has a
     plausible match in the body must appear in the outline with the same
     `logical_index`; missing matches must be reported as a review zone.
  4. Headings level hierarchy must be monotonically consistent (no H1 inside
     a chapter unless it is a new chapter).
  5. For every input paragraph, return `paragraph_anchors[i] = {role, level,
     confidence}`. Roles must be drawn from the existing taxonomy.
  6. Return `review_zones` for any region where the model's confidence is
     below `medium`.
- Output: a single JSON object matching the `DocumentMap` schema.

The user prompt provides:
- the full descriptor list (or sampled list);
- a short summary block: total paragraph count, sampled flag,
  document-level stats (median font size, dominant style cluster,
  number of pages if known).

#### Caching and artifact

`DocumentMap` is cached under `.run/document_maps/<cache_key>.json` using the
same key construction approach as `_build_structure_map_cache_key(...)` in
`src/docxaicorrector/processing/preparation.py:345`, plus a stage tag.

The artifact contains the full `DocumentMap` payload, the model name,
`sampled` flag, sampled logical indexes, token usage, processing time, prompt
version, descriptor schema version, and coordinate schema version.

#### Stage 1 output validation

The Stage 1 model output is accepted only after deterministic validation:

- it must be a JSON object matching the `DocumentMap` schema;
- every role must be in the existing `_VALID_AI_ROLES` taxonomy;
- every confidence must be `high`, `medium`, or `low`;
- every referenced logical index must exist in the input descriptor set or in
  the complete paragraph coordinate set when sampling was used;
- heading levels are integers in `1..6` for heading anchors and `null` for
  non-heading anchors;
- TOC and review-zone ranges must be ordered and bounded by known logical
  indexes.

If validation fails, the implementation may retry once with a compact schema
error summary. If the retry also fails, Stage 1 returns no `DocumentMap`, saves
the malformed-output artifact, logs the failure, and Stage 2 falls back to the
legacy non-anchored classifier.

### Stage 2 — Anchored Classification

The existing `build_structure_map(...)` is reused. Two changes:

1. `build_paragraph_descriptors(...)` accepts an optional
   `document_map: DocumentMap | None`. When provided, each descriptor
   includes:
   ```
   "anchor_r":  <DocumentMapAnchor.role>,
   "anchor_l":  <DocumentMapAnchor.heading_level>,
   "anchor_c":  <DocumentMapAnchor.confidence>
   ```
2. The system prompt at
   `prompts/structure_recognition_system.txt` is extended with a final
   block titled "Anchor consistency rules":
   - If `anchor_c == "high"`, you must keep the anchor role and level unless
     the local text content is clearly inconsistent. Confidence of any change
     must be at most `medium`.
   - If `anchor_c == "medium"`, you may refine within the same role family,
     but you must not promote `body` to `heading` without strong local
     evidence.
   - If `anchor_c == "low"`, you may freely classify locally.

Window parameters change:

- `max_window_paragraphs` targets **3000** when an anchor is present.
- `overlap_paragraphs` defaults to **0** when an anchor is present.
- `_DESCRIPTOR_PREVIEW_CHARS` may increase up to **1500** when an anchor is
  present.

These changes are conditional: if `document_map is None`, the legacy
behaviour (1800 / 50 / 600) is preserved.

Anchored windowing is token-budgeted, not purely count-based. The target
`3000 / 1500 / 0` profile is acceptable for moderate documents and avoids the
legacy overlap cost, but the implementation must estimate prompt size before
the call and reduce window size or preview length to fit
`structure_recovery.anchored_classification.target_input_tokens`. The existing
fallback split on provider errors remains only a safety net, not the primary
budgeting mechanism.

The anchored structure-map cache key includes the document-map cache key or
anchor fingerprint, prompt version, descriptor schema version, coordinate
schema version, preview length, window parameters, and target token budget.

### Stage 3 — Reconciliation

New module: `src/docxaicorrector/structure/reconciliation.py`.

Public function:

```
def reconcile_with_document_map(
    paragraphs: list[ParagraphUnit],
    document_map: DocumentMap,
    structure_map: StructureMap,
) -> tuple[StructureMap, ReconciliationReport]
```

`reconcile_with_document_map(...)` is deterministic and does not call the AI.
It returns a patched `StructureMap` plus a `ReconciliationReport`. The patched
map may contain deterministic corrections only when they are direct projections
of high-confidence `DocumentMap` anchors and stay within the existing role
taxonomy. Medium-confidence anchors remain advisory-only Stage 2 inputs and may
surface through divergence reporting or targeted recall, but they do not patch
`StructureMap` on their own. The function does not mutate `ParagraphUnit`
directly.

Deterministic checks:

1. For every `DocumentMapOutlineEntry`, find a `ParagraphUnit` with
   `logical_index == entry.logical_index`. It must end up classified as
   `heading` with `heading_level == entry.level` after Stage 2. If not, the
   entry is recorded as `missing_outline_entry`.
2. For every `ParagraphUnit` classified as `heading` after Stage 2 that does
   not appear as an outline entry, record `unexpected_heading`.
3. For every `DocumentMapTocEntry`, the `candidate_body_logical_index` must
   exist as a `heading` after Stage 2 within ±5 paragraphs. If not, record
   `toc_entry_without_body_match`.
4. The `body_start_logical_index` must be respected: every paragraph with
   `logical_index < body_start_logical_index` must end up with
   `structural_role` in `{toc_entry, toc_header, dedication, epigraph, attribution}`
   or `is_repeated_across_pages == True`. If not, record
   `front_matter_leak`.

Targeted re-classification is a separate optional function:

```
def targeted_reclassify_with_reconciliation_context(
    paragraphs: list[ParagraphUnit],
    document_map: DocumentMap,
    structure_map: StructureMap,
    report: ReconciliationReport,
    *,
    client: object,
    model: str,
    timeout: float,
) -> StructureMap
```

- If `len(missing_outline_entry) + len(unexpected_heading) >
  reconciliation_targeted_threshold` (default 3), one additional bounded
  AI call is allowed.
- Input: only the union of paragraphs flagged by reconciliation, padded by
  ±2 neighbours.
- Hard cap: `reconciliation_targeted_max_paragraphs` (default 60).
- The model receives the same descriptor as Stage 2, plus the
   `ReconciliationReport` flags.
- The model's output is constrained to update roles only inside that set.
- Feature flag: `structure_recovery_reconciliation_targeted_enabled`.
- Targeted output passes the same role/confidence/index validation as Stage 2.
- The final `StructureMap` is applied exactly once through `apply_structure_map(...)`.

`ReconciliationReport` fields:

```
@dataclass(frozen=True)
class ReconciliationReport:
    missing_outline_entries: tuple[int, ...]
    unexpected_headings: tuple[int, ...]
    toc_entries_without_body_match: tuple[int, ...]
    front_matter_leaks: tuple[int, ...]
    targeted_recall_invoked: bool
    targeted_recall_count: int
    outline_coverage_ratio: float    # matched outline entries / total outline entries
```

The artifact is saved at `.run/reconciliation_reports/<cache_key>.json`.

### Validation and gating (two phases, unchanged readiness contract)

AI-first orchestration uses two validation phases:

1. Pre-AI diagnostic validation runs after extraction/signals and before Stage
   1. It is used only to decide whether escalation is needed in `auto` mode and
   to preserve the existing diagnostic artifact trail.
2. Post-AI readiness validation runs after Stage 3 and after the final
   `StructureMap` has been applied. This report drives publication gating.

The readiness contract from `_build_readiness_status(...)` in
`src/docxaicorrector/structure/validation.py:210` is unchanged. The
post-AI `StructureValidationReport` is supplemented with two new advisory
fields:

```
document_map_present: bool
outline_coverage_ratio: float | None
```

These are persisted in the existing
`.run/structure_validation/<timestamp>.json` artifact.

## Configuration

Add to `config.toml`:

```
[structure_recovery]
mode = "ai_first"            # "legacy" | "ai_first"
enabled = false              # feature flag for the whole AI-first path

[structure_recovery.document_map]
enabled = false
model = ""                   # falls back to the resolved structure-recognition model
timeout_seconds = 120
max_input_paragraphs = 6000  # threshold for hierarchical sampling
max_input_tokens = 180000
preview_chars = 120
cache_enabled = true
save_debug_artifacts = true

[structure_recovery.anchored_classification]
max_window_paragraphs = 3000
overlap_paragraphs = 0
preview_chars = 1500
target_input_tokens = 180000
min_confidence = "medium"

[structure_recovery.reconciliation]
targeted_enabled = false
targeted_threshold = 3
targeted_max_paragraphs = 60
targeted_timeout_seconds = 60
```

`[structure_recognition]` keys remain as today and continue to drive the
legacy path. When `structure_recovery.enabled = false`, the legacy path runs
exactly as today.

Resolved `app_config` keys are flat, following the current `ApplicationConfig`
style. Environment override names use the `DOCX_AI_STRUCTURE_RECOVERY_*`
prefix. Clamp ranges and defaults are covered by config-loader tests in the
same style as `[structure_recognition]` and `[structure_validation]`.

## AI Budget Contract

Per document, the AI-first path is bounded by:

- 1 Stage 1 call (Document Map).
- N Stage 2 calls, where N is determined by token-budgeted anchored windows and
  is approximately `ceil(nonempty_paragraphs / 3000)` for moderate documents.
- ≤1 Stage 3 targeted call (only if enabled and threshold exceeded).

For a typical 3000-paragraph PDF book, this is **2–3 AI calls total**, against
1–2 calls today, but with a global outline pass that today's pipeline lacks.
For very large documents with sampling, Stage 1 stays at 1 call and Stage 2
grows linearly.

A hard cap is enforced inside `build_document_map(...)`:
`total_input_tokens_estimate <= structure_recovery.document_map.max_input_tokens`
(default 180000). If exceeded, sampling density is reduced until the
descriptor list fits.

A hard cap is also enforced before each anchored Stage 2 call:
`total_input_tokens_estimate <= structure_recovery.anchored_classification.target_input_tokens`
(default 180000). If exceeded, the implementation first reduces preview length
and then reduces the descriptor window size. The existing provider-error split
fallback is retained for unexpected provider limits.

## Module Boundaries

- `document/extraction.py` — extraction + signal computation.
- `document/layout_cleanup.py` — flag computation only.
- `document/structure_repair.py` — flag computation only.
- `document/relations.py` — flag computation only (TOC region detection
  becomes a hint, not a binding).
- `structure/document_map.py` — Stage 1.
- `structure/recognition.py` — Stage 2 (anchored windowed classifier).
- `structure/reconciliation.py` — Stage 3.
- `structure/validation.py` — gating, unchanged contract, new advisory fields.
- `processing/preparation.py` — orchestration.

Dependency rule:

- `structure/*` may consume `document/*` and `core/*`.
- `document/*` may not consume `structure/*`.
- `processing/preparation.py` is the only allowed place to call any of
  Stages 1, 2, 3 in sequence.

## Implementation Slices

The order of slices is dictated by dependency, not by visible payoff.

### Slice 0 — Plumbing, mode separation, and coordinates

Affected files:

- `src/docxaicorrector/core/config.py` — add flat `ApplicationConfig` fields
  for `[structure_recovery]` and nested sections.
- `src/docxaicorrector/core/config_structure_sections.py` — parse defaults,
  env overrides, clamps, and validation for structure recovery settings.
- `config.toml` — add disabled-by-default structure recovery settings.
- `src/docxaicorrector/core/models.py` — add `logical_index` and report fields
  needed to distinguish flagged vs removed cleanup counts.
- `src/docxaicorrector/document/extraction.py` — propagate structure recovery
  mode through `app_config`, assign stable `logical_index`, and keep legacy
  helper behaviour when AI-first is disabled.
- `src/docxaicorrector/processing/preparation.py` — include recovery mode and
  coordinate schema version in prepared-source and structure-related cache keys.
- Tests for config loading, disabled-mode legacy parity, unique logical indexes,
  and cleanup status text.

Verification:

- `bash scripts/test.sh tests/ -q` clean.
- A targeted disabled-mode parity test proves that
  `structure_recovery.enabled = false` preserves the same paragraph count,
  role fields, cleanup status note, and structure-recognition descriptor keys
  as the current legacy path.
- A duplicate-`source_index` regression fixture proves that `logical_index` is
  unique and is the key used by Stage 1/2/3 contracts.

### Slice 1 — Stage 0 contract

Affected files:

- `src/docxaicorrector/core/models.py` — add new signal fields on
  `ParagraphUnit` (currently 32 fields, none collide with the new names except
  that `logical_index` was introduced in Slice 0).
- `src/docxaicorrector/document/layout_cleanup.py` — switch from deletion to
  flagging in `clean_paragraph_layout_artifacts(...)` only when AI-first
  signal mode is active; add `cleanup_mode` and `flagged_*` counters while
  keeping `removed_*` literal.
- `src/docxaicorrector/document/structure_repair.py` — strip role mutation
  branches at lines 97–100, 221–248, 267–275 and split/clone role assignment
  at 309–404 in AI-first mode; keep detection as signals and keep
  boundary-level merging of isolated bullet glyphs only before `logical_index`
  assignment.
- `src/docxaicorrector/document/roles.py` —
  `promote_short_standalone_headings(...)` and
  `normalize_front_matter_display_title(...)` switched to writing
  `heuristic_role_hint` / `heuristic_heading_level_hint` rather than
  `role` / `heading_level` in AI-first mode. Legacy mode remains unchanged.
- `src/docxaicorrector/document/extraction.py` — non-explicit heuristic roles
  from `_build_raw_paragraph(...)` are copied into advisory hints and cleared
  from binding structural fields in AI-first mode; explicit DOCX headings stay
  authoritative.
- `src/docxaicorrector/document/relations.py` — no role-mutation changes
  required (verified that `apply_relation_side_effects(...)` only
  mutates `attached_to_asset_id`).
- Tests in `tests/` that assert paragraph deletion in legacy
  `clean_paragraph_layout_artifacts(...)` or role mutation in
  `repair_pdf_derived_structure(...)` /
  `promote_short_standalone_headings(...)` /
  `normalize_front_matter_display_title(...)` are split into legacy assertions
  and AI-first signal-mode assertions. Signal-mode tests assert flag/hint
  values and unchanged paragraph counts.

Verification:

- `bash scripts/test.sh tests/ -q` clean.
- Structure-scoped diagnostics on `lietaer-pdf-first-20-structure-core`
  (`tests/sources/Rethinking-money-first-20-pages.pdf`) must preserve the same
  paragraph count post-extraction in AI-first mode and unchanged legacy output
  when AI-first is disabled.
- The same document is the canonical real-document proof path for Slice 1; do
  not widen routine verification to a second corpus document during ordinary
  development on this spec.

### Slice 2 — Stage 1 Document Map

Affected files:

- `prompts/document_map_system.txt` (new).
- `src/docxaicorrector/structure/document_map.py` (new).
- `src/docxaicorrector/core/models.py` — `DocumentMap*` dataclasses.
- `src/docxaicorrector/processing/preparation.py` — gated call to
  `build_document_map(...)` after pre-AI diagnostic validation and before
  anchored recognition.
- New artifact directory `.run/document_maps/`.

Verification:

- Unit tests for sampling and schema validation.
- Unit tests for malformed JSON retry/fallback, invalid role rejection,
  invalid logical-index rejection, and artifact persistence.
- Structural preparation diagnostic on `lietaer-pdf-first-20-structure-core`:
  artifact `.run/document_maps/<key>.json` must contain a non-empty outline and
  a bounded TOC region.

### Slice 3 — Stage 2 anchoring

Affected files:

- `src/docxaicorrector/core/models.py` — extend
  `ParagraphDescriptor.to_prompt_dict(...)` with optional anchor fields.
- `src/docxaicorrector/structure/recognition.py` — accept
  `document_map: DocumentMap | None` in `build_paragraph_descriptors(...)`
  and `build_structure_map(...)`; switch window/overlap/preview defaults
  conditionally.
- `prompts/structure_recognition_system.txt` — append "Anchor consistency
  rules" block.
- `src/docxaicorrector/processing/preparation.py` — pass `DocumentMap` into
  the structure recognition call when `structure_recovery.enabled = true`.

Verification:

- Behaviour parity test: when `document_map is None`, the descriptor and
  prompt are byte-identical to the legacy path.
- Anchored test: when anchors are provided, descriptors carry `anchor_*`
  fields, overlap is 0, and window sizing respects the configured token budget.

### Slice 4 — Stage 3 reconciliation

Affected files:

- `src/docxaicorrector/structure/reconciliation.py` (new).
- `src/docxaicorrector/processing/preparation.py` — call after Stage 2,
  before post-AI `validate_structure_quality(...)`.
- `.run/reconciliation_reports/`.
- `src/docxaicorrector/structure/validation.py` — read
  `outline_coverage_ratio` and persist it as an advisory field; do not
  change readiness logic.

Verification:

- Synthetic document where TOC lists 10 chapters but Stage 2 produces only 7
  headings: `outline_coverage_ratio == 0.7`,
  `missing_outline_entries` has 3 indexes; if targeted recall is enabled,
  Stage 3 must invoke once and reduce the gap.
- Deterministic reconciliation test proves `reconcile_with_document_map(...)`
  returns `(StructureMap, ReconciliationReport)` and does not mutate
  `ParagraphUnit` directly.

### Slice 5 — Heuristic deprecation

After two consecutive successful structure-scoped checkpoints on canonical
profile `lietaer-pdf-first-20-structure-core` with
`structure_recovery.enabled = true`, remove the dead branches in
`structure_repair.py` and `layout_cleanup.py` that previously mutated roles.
If a late full-tier checkpoint is still needed, it is optional and must be run
only after the structure-scoped checkpoints are already green and only when the
remaining risk is proven to live in final output artifacts rather than
preparation/structure artifacts.

This slice is intentionally last and intentionally explicit. The repository
has historically accumulated heuristics; this slice exists specifically to
shrink that surface.

## Verification Plan

Canonical commands. No PowerShell substitutions.

1. `bash scripts/test.sh tests/ -q`
2. `bash scripts/run-structural-preparation-diagnostic.sh lietaer-pdf-first-20-structure-core`
3. Optional benchmark rerun in
  `benchmark_projects/structure_recognition_benchmark/` against
  `lietaer-pdf-first-20-structure-core`.
4. Optional late checkpoint only when a defect is proven to exist in final
  markdown/DOCX artifacts rather than in preparation artifacts:
  `bash scripts/run-real-document-validation.sh` with
  `DOCXAI_REAL_DOCUMENT_PROFILE=lietaer-pdf-first-20-structure-core` and an
  explicitly chosen run profile appropriate for that checkpoint.

### Structure-Recovery Corpus Policy

This spec is about AI-first structure recovery, not about general translation
or literary-edit quality. Its real-document verification set must therefore be
structure-relevant and cheap enough for routine iteration.

Canonical document for this spec:

1. `lietaer-pdf-first-20-structure-core`
  (`tests/sources/Rethinking-money-first-20-pages.pdf`) is the default fast
  PDF slice for ordinary structure work. It is the primary real-document loop
  because it is English-source, PDF-derived, already contains front matter,
  TOC, and body structure, is short enough for repeated diagnostics, and is
  already registered in `corpus_registry.toml`.
2. `lietaer-pdf-full-benchmark` is a late checkpoint profile only. It is not
  part of the routine inner loop for this spec.

Explicit exclusions for the ordinary inner loop:

1. `lietaer-core` (`tests/sources/Лиетар глава1.docx`) is not the canonical
  structure-recovery regression document for this spec. It may remain useful in
  broader repository validation, but it is not representative of the PDF-first
  structure problems this spec is solving.
2. `ui-parity-default`, `ui-parity-ai-default`, and
  `ui-parity-translate-benchmark-advisory` are full-tier processing profiles.
  They are not default evidence for structure-only work.
3. `ui-parity-pdf-structural-recovery` remains a full-tier translate profile
  with `structure_recognition_mode = "off"`; despite its legacy name, it is
  not a valid ordinary-loop proof path for AI-first structure-recognition work.
4. `tests/sources/The Value of Everything. Making and Taking in the Global Economy by Mariana Mazzucato (z-lib.org).pdf`
  exists in the repository and is a good future English-source control
  candidate, but it must not become canonical evidence for this spec until a
  dedicated corpus entry with explicit structure expectations is registered in
  `corpus_registry.toml`.

### Structure-Work Inner Loop

When the active task is specifically AI-first structure recovery, the default
verification loop must stay structure-scoped and cost-bounded.

Rules:

1. The default inner loop is: focused local structure tests plus structural
  diagnostics. Do not use the full real-document validator as the ordinary
  debug loop for paragraph-role, anchor, reconciliation, or readiness-gate
  changes.
2. Prefer the narrowest affected test file or node selector first, for example
  `tests/test_document_map.py`, `tests/test_structure_recognition.py`,
  `tests/test_structure_reconciliation.py`, `tests/test_structure_validation.py`,
  or the directly affected selector in `tests/test_preparation.py`.
3. When a change needs real-document evidence for preparation-stage structure
  behavior, prefer `bash scripts/run-structural-preparation-diagnostic.sh ...`
  over the full validator. This is the default real-document path for
  inspecting Document Map output, anchored classification inputs, reconciliation
  signals, and preparation snapshots.
4. The default structural diagnostic document is always
  `lietaer-pdf-first-20-structure-core`. Do not branch the ordinary inner loop onto
  a second corpus document just because the defect involves TOC or front matter;
  this canonical PDF slice already contains those structures.
5. The full validator is reserved for milestone checkpoints before closing a
  major slice, or for bugs already demonstrated to exist only in the final
  markdown/DOCX artifact rather than in structure/preparation artifacts.
  When that happens, prefer the smallest relevant corpus document first; for
  this spec that means `lietaer-pdf-first-20-structure-core` before any full-book
  profile.
6. Do not use `lietaer-core` full DOCX validation as the routine proof path for
  this spec's day-to-day work.
7. If a bug is visible in preparation snapshots, structure-validation artifacts,
  reconciliation reports, or structural diagnostics, fix and verify it there
  before spending a full-validator run.
8. Any full-validator rerun during this spec should be intentional and rare,
  because the `full` tier executes the complete document-processing path rather
  than only structure recognition, and therefore carries materially higher
  external model cost.

Recommended verification sequence while implementing this spec:

1. Run the narrowest affected structure test selector.
2. Run the directly affected structure test file.
3. Run `bash scripts/run-structural-preparation-diagnostic.sh lietaer-pdf-first-20-structure-core`
  for the default real-document structure snapshot.
4. Run a full-tier validator only as a checkpoint for a completed stage, or
  when the defect is proven to exist only in final output artifacts.

For each canonical profile, the spec defines the following
acceptance metric:

- **Outline coverage ratio** (computed by `reconcile_with_document_map(...)`):
  fraction of `DocumentMapOutlineEntry` items that resolve to a heading
  classified by Stage 2.

Acceptance thresholds for the AI-first path:

- `lietaer-pdf-first-20-structure-core`: outline coverage ≥ 0.9 and
  `front_matter_leaks == ()`.
- `lietaer-pdf-full-benchmark`: outline coverage ≥ 0.9 and
  `front_matter_leaks == ()` when a late optional full-book checkpoint is used.

## Safety and Rollback

- `structure_recovery.enabled = false` keeps the legacy path bit-for-bit.
- `structure_recovery.document_map.enabled = false` disables Stage 1 even
  when the AI-first orchestration is active; in that case Stage 2 falls
  back to legacy descriptors and the spec's improvements do not apply.
- `structure_recovery.reconciliation.targeted_enabled = false` disables the
  bounded re-classification AI call.
- All three stages save artifacts; rollback is purely a config flip.
- No persisted user data is changed by this spec.

## What Does Not Change

- The role taxonomy in `_VALID_AI_ROLES` is unchanged.
- The readiness contract in `validate_structure_quality(...)` and
  `_build_readiness_status(...)` is unchanged.
- The segment detection contract in
  `detect_document_segments(...)` is unchanged.
- All existing artifact directories under `.run/` are preserved.
- The resolved structure-recognition model continues to be the model role
  used for Stages 1–3 unless an explicit override is set.
- The legacy non-anchored path remains supported as the rollback target.

## Why This Is The Final Direction

The current architecture has a structural mismatch: failures are global,
the AI is given a local task, and the heuristic layer sits between the
data and the AI. Each new difficult document forces a new heuristic rule.

This spec inverts the order:

- the AI sees the whole document first,
- builds a single global map,
- and the rest of the pipeline projects from that map.

Heuristics shrink to signal extraction. The AI becomes the structural
reasoner. New difficult documents do not require new code paths; they
require, at most, a better Stage 1 model or prompt, both of which are
configuration changes rather than heuristic engineering.

The spec does not eliminate the existing windowed classifier; it anchors it.
That preserves the ability to revert to the legacy path through a single
config flag and limits the blast radius of every slice.

## Implementation Guardrails for Agents

This section is normative for any human or AI agent implementing or debugging
this spec.

The goal of this work is **not** to make heuristics smarter until they solve
structure recovery again. The goal is to make the AI-first map the component
that can correct global structural failures after Stage 2. Heuristics are
allowed to expose evidence; they are not allowed to become the structural
reasoner.

### Authority rule

When behaviour is ambiguous, preserve this authority order:

1. Non-structural asset invariants (`image`, `table`, and safe caption
   attachment contracts).
2. High-confidence `DocumentMap` anchors, outline entries, TOC region, and
   `body_start_logical_index` from Stage 1.
3. Stage 3 reconciled `StructureMap` patches and targeted-recall output.
4. Stage 2 anchored local classifications.
5. Explicit DOCX heading metadata, unless an audited high-confidence Stage 3
   reconciliation patch overrides it.
6. Stage 0 heuristic hints and layout signals as advisory evidence only.

`heuristic_role_hint`, `heuristic_structural_role_hint`,
`heuristic_heading_level_hint`, `heuristic_list_kind_hint`,
`heuristic_embedded_structure_hints`, `toc_pattern_hint`,
`is_likely_page_number`, and `is_repeated_across_pages` are signals. They may
help Stage 1/2 prompts, sampling, diagnostics, and targeted recall selection.
They must not be treated as final structural truth in the post-AI path unless
the `DocumentMap` or reconciled `StructureMap` projects the same decision.

### Forbidden implementation direction

Agents must not fix structure-recovery defects by adding another document-
specific or pattern-specific heuristic that assigns final roles, final heading
levels, final TOC boundaries, or final front-matter/body boundaries.

Forbidden examples:

- adding new regex branches that promote/demote `ParagraphUnit.role` or
  `heading_level` before Stage 1;
- making `heuristic_structural_role_hint` behave as the final
  `structural_role` in post-AI validation, segmentation, semantic-block
  grouping, or relation building;
- adding document-specific exceptions for one PDF title, TOC phrase, font
  pattern, scripture/reference shape, or chapter-name format;
- widening Stage 0 cleanup/repair until the old heuristic path passes a
  diagnostic while Stage 1/2/3 remain weak;
- silently falling back from AI-first to current heuristic roles without an
  explicit degraded status, artifact, and log event.

### Required implementation direction

When a failure is global in nature (front matter end, TOC region, outline
coverage, chapter-level hierarchy, body-start drift, TOC/body alignment, or
Stage 2 disagreement with Stage 1), agents must first look for an AI-first
fix:

1. Improve the Stage 1 `DocumentMap` prompt, descriptor schema, sampling
   priority, output validation, or postprocessing.
2. Improve how Stage 2 descriptors carry `DocumentMap` anchors and advisory
   signals.
3. Improve Stage 2 anchor consistency instructions or token budgeting only when
   the local classifier lacks the right context from Stage 1.
4. Improve Stage 3 reconciliation, anchor-conflict reporting, targeted recall
   selection, or audited patch application.
5. Improve artifacts and diagnostics so the next failure is visible as a
   `DocumentMap`/anchor/reconciliation problem, not hidden as a heuristic
   fallback.

Only after those paths are proven insufficient may deterministic code be
changed, and then only as signal extraction, validation of AI output, bounded
budgeting, cache invalidation, artifact persistence, or audited projection of
AI decisions.

### Acceptable deterministic changes

Deterministic code may:

- compute signals that are exposed to Stage 1/2 (`font_size_z_score`, style
  clusters, page-number flags, repeated-furniture flags, TOC-pattern hints,
  embedded fragment hints);
- validate AI output schemas and reject impossible indexes, roles, ranges, or
  heading levels;
- enforce safety around assets and captions;
- reconcile high-confidence `DocumentMap` decisions into a final
  `StructureMap` with explicit report fields;
- mark an AI-first run as degraded when Stage 1/2/3 cannot produce a reliable
  result.

Deterministic code may not become a parallel structure recognizer that competes
with the `DocumentMap`.

### Prompt guidance for coding agents

When asking an AI coding agent to work on this area, include the following
instruction block verbatim or in equivalent form:

```text
This is AI-first structure recovery work. Do not solve the issue by adding or
tuning heuristics that make Stage 0 decide roles, headings, TOC boundaries, or
front-matter/body boundaries. Stage 0 may only expose advisory signals. If the
bug is structural or global, first inspect and improve the Stage 1 DocumentMap
prompt/descriptors/sampling/validation, Stage 2 anchor use, or Stage 3
reconciliation/targeted recall. Any deterministic change must either extract a
signal, validate AI output, preserve artifacts/cache correctness, or apply an
audited high-confidence DocumentMap/reconciliation decision. Do not make
heuristic hints final authority in the post-AI path.
```

### Review checklist for future changes

Before accepting a change in this area, verify:

- Does it make a heuristic decide final structure? If yes, reject or redesign
  it as a signal.
- Does it make `DocumentMap` more capable of correcting the failure? If no,
  explain why an AI-first fix was not possible.
- Does post-AI code distinguish advisory hints from applied AI structure? If
  no, add an explicit phase/source boundary.
- Does fallback from Stage 1/2/3 produce an auditable degraded status rather
  than silently using current rules? If no, add the status/artifact/log event.
- Does the test assert the AI-first authority path, not just the heuristic
  symptom? If no, add a test around `DocumentMap`, anchors, reconciliation, or
  post-AI application.

## Open Authority-Boundary Work

The implementation checklist below records completed slices, but the AI-first
authority boundary is not fully hardened yet. Stage 0 no longer mutates roles in
the main paths, Stage 1/2/3 use `logical_index`, targeted hallucinated indexes
are handled gracefully, and `outline_coverage_ratio` is explicitly advisory.
However, the implementation can still let old heuristic evidence act as final
structure, let local Stage 2/application guards block the global `DocumentMap`,
or fall back to current rules without a clear degraded AI-first contract.

The following findings are the full current principle-level backlog. They are
not requests to tune heuristics. They are the remaining work needed to ensure
that the AI-first map corrects global structural failures after Stage 2 instead
of becoming an advisory layer on top of the old heuristic architecture.

### 1. Keep heuristic hints out of final structural authority

Current risk:

- Stage 0 now writes hints rather than mutating binding fields, but downstream
  modules may still treat `heuristic_structural_role_hint` as the effective
  structural role.
- This can make a heuristic TOC/front-matter guess influence post-AI validation,
  semantic-block splitting, segment detection, or relation grouping as if it
  were a final `DocumentMap`/Stage 3 decision.

Required direction:

1. Split helper APIs into explicit concepts: binding structural state, advisory
   Stage 0 hints, and final AI-applied structure.
2. Make post-AI paths read binding roles from the applied `StructureMap`, not
   heuristic hints, unless they are explicitly running in a pre-AI diagnostic
   mode.
3. If a downstream module needs hint evidence, pass an explicit phase/source
   argument such as `pre_ai_diagnostic` vs `post_ai_final`.
4. Add tests proving that post-AI validation/segmentation/block grouping do not
   treat `heuristic_structural_role_hint="toc_entry"` as final structure unless
   the `DocumentMap`/reconciled `StructureMap` projects the same role.

Recommended target areas:

- `structure/validation.py` effective structural role helpers.
- `document/relations.py` TOC-region relation detection.
- `document/semantic_blocks.py` structural block splitting.
- `document/segments.py` TOC/heading boundary helpers.

### 2. Move high-anchor conflict arbitration out of local heuristics

Current risk:

- Stage 2/application currently uses local prose-like/heading-like checks to
  decide whether a classification may disagree with a `DocumentMap` anchor.
- This lets local deterministic heuristics become an arbiter over the global
  `DocumentMap` instead of merely reporting anchor conflicts for Stage 3.

Required direction:

1. Treat Stage 2 classifications as proposals when they conflict with high- or
   medium-confidence `DocumentMap` anchors.
2. Record anchor conflicts explicitly instead of silently accepting or dropping
   them through local prose/heading heuristics.
3. Let Stage 3 reconciliation decide which conflicts become final patches.
4. If local override logic is retained, it must be audited in the
   reconciliation report as `accepted_local_overrides` / `rejected_local_overrides`,
   not hidden inside `apply_structure_map(...)`.

### 3. Let audited Stage 3 patches override locked legacy state safely

Current risk:

- `apply_structure_map(...)` skips paragraphs whose `role_confidence` is
  `explicit` or `adjacent` before checking whether the classification is a
  high-confidence `document_map_reconciliation` patch.
- As a result, old extraction-time authority can still block the global
  `DocumentMap` from correcting a real structural failure.

Required direction:

1. Keep ordinary Stage 2 local classifications blocked from overwriting
   `explicit` / `adjacent` roles.
2. Add a narrow exception for audited Stage 3 reconciliation patches when all
   of these are true:
   - `document_map is not None`;
   - `classification.rationale == "document_map_reconciliation"`;
   - `classification.confidence == "high"`;
   - the matching `DocumentMap` anchor is `high` confidence;
   - the patch role and heading level match that anchor;
   - the paragraph is not an unsafe asset boundary such as `image` or `table`;
   - caption overrides remain protected unless the patch preserves `caption`.
3. Return explicit metrics for applied/skipped reconciliation overrides, for
   example `reconciliation_locked_overrides_applied` and
   `reconciliation_locked_overrides_skipped`.
4. Add tests proving that ordinary AI does not override locked roles, while a
   valid high-confidence Stage 3 patch can, and unsafe locked patches are
   skipped with audit metrics.

This keeps `DocumentMap` as the final global reasoner without making Stage 3 an
unbounded role rewrite mechanism.

### 4. Make post-AI validation phase-aware

Current risk:

- Post-AI validation still computes some readiness/risk facts from old
  heuristic counters and effective-role helpers that may prioritize hints.
- This can let Stage 0 evidence make post-AI readiness look better or worse
  independently of the `DocumentMap`/reconciled `StructureMap` result.

Required direction:

1. Make `validate_structure_quality(...)` phase-aware, for example
   `pre_ai_diagnostic` vs `post_ai_readiness`.
2. In pre-AI diagnostic mode, hints may be used to decide whether escalation is
   needed.
3. In post-AI readiness mode, validation should use applied binding roles and
   explicit reconciliation/report fields, not heuristic hints as final facts.
4. Keep `document_map_present` and `outline_coverage_ratio` advisory unless the
   readiness contract is intentionally revised in a separate slice.

### 5. Split strict front-matter leaks from AI-approved front-matter body advisories

Current risk:

- `front_matter_leaks` currently treats any pre-body paragraph outside a small
  role whitelist as a leak.
- A `DocumentMap` may intentionally anchor front-matter prose as `body` before
  `body_start_logical_index`, but deterministic leak logic can still punish it.

Required direction:

1. Keep `front_matter_leaks` for dangerous contradictions such as unexpected
   headings/lists/body-start drift before the mapped body start.
2. Add a separate advisory bucket, for example
   `front_matter_body_advisories`, for body-like paragraphs that the
   `DocumentMap` anchors as `body` with medium/high confidence before body
   start.
3. Keep acceptance metrics focused on `front_matter_leaks == ()`, while
   surfacing advisories separately in artifacts.

### 6. Stop creating final TOC-region relations from pre-AI heuristic hints

Current risk:

- Relation normalization can create accepted TOC-region relations from
  `heuristic_structural_role_hint` before Stage 1 decides the actual TOC region.
- Even if relation side effects do not mutate roles, artifacts can present a
  heuristic TOC relation as accepted structure.

Required direction:

1. In AI-first mode, pre-AI relation normalization may emit TOC candidate
   diagnostics, not final TOC-region relations.
2. Final TOC-region relation artifacts, if needed, should be projected from
   `DocumentMap.toc_region` after Stage 1/3.
3. Add a relation authority/source field or distinct relation kinds such as
   `toc_region_candidate` vs `toc_region`.

### 7. Make default/fallback DocumentMap status explicit

Current risk:

- A missing or failed Stage 1 map can degrade to `document_map=None` or a
  body-only low-confidence default, after which the system can continue through
  local classification/current rules.
- In canonical AI-first mode, that hides the loss of global structure authority.

Required direction:

1. Represent Stage 1 result status explicitly, for example `ai`, `cache`,
   `default`, `unavailable`, or `degraded`.
2. Persist the status and reason in document-map artifacts, structural
   diagnostics, and processing outcome logs.
3. If `structure_recovery.enabled=true` and Stage 1 is enabled, Stage 1 failure
   must be visible as AI-first degraded execution, not as ordinary heuristic
   success.

### 8. Keep prompts from over-trusting heuristic hints

Current risk:

- Stage 1/2 prompts mark embedded hints as advisory, but they do not strongly
  state that Stage 0 hints are fallible and lower priority than global
  consistency.

Required direction:

1. In `prompts/document_map_system.txt`, add an evidence hierarchy: global
   consistency across body start, TOC, outline, typography, and repeated patterns
   outranks Stage 0 hints.
2. In `prompts/structure_recognition_system.txt`, state that high-confidence
   `DocumentMap` anchors and outline consistency outrank local heuristic hints.
3. When hints conflict with global structure, prompts should tell the model to
   ignore the hints and mark the conflict in review zones or rationale.

### 9. Use DocumentMap review zones and anchor conflicts for targeted recall

Current risk:

- Targeted recall is currently driven mainly by reconciliation report lists such
  as missing outline entries and unexpected headings.
- Stage 1 `review_zones`, high-confidence anchor conflicts, and body-start/TOC
  boundary uncertainty may not be selected unless they appear as one of those
  downstream symptoms.

Required direction:

1. Extend reconciliation reporting with anchor disagreement context for
  targeted recall. Canonical readers should use
  `anchor_disagreements_seen`; the deprecated compatibility alias
  `anchor_conflicts` has been removed on the reconciliation schema bump after
  downstream readers, docs, tests, and artifact expectations were updated.
  If needed, also add `review_zone_targeted_indexes`.
2. Include high-severity `DocumentMap.review_zones`, `body_start_logical_index`
   neighbourhood, and TOC boundary neighbourhoods in targeted recall candidate
   selection, still bounded by `targeted_max_paragraphs`.
3. Record why each targeted paragraph was selected, so artifacts show whether
   targeted recall was driven by outline coverage, TOC/body mismatch, anchor
   conflict, front-matter leak, or review-zone uncertainty.

### 10. Make AI-first fallback auditable and stage-specific

Current risk:

- A broad Stage 1/2/3 exception can fall back to current paragraph roles and
  emit a generic heuristic/current-rules message.
- In canonical AI-first mode, this can hide the fact that the global map failed
  and the run no longer has AI-first structure authority.

Required direction:

1. Replace broad structure-recognition fallback with stage-specific handling:
   Stage 1 provider/schema failure, Stage 2 provider/window failure, Stage 3
   reconciliation failure, artifact failure, and application failure should be
   distinguishable.
2. Provider/time-budget failures may degrade to a fallback path, but must emit
   `ai_first_degraded = true`, `fallback_stage`, `document_map_present`, and a
   precise reason in logs/artifacts.
3. Reconciliation/application invariant failures should not be silently
   converted into “current rules”; they should either block AI-first structure
   recovery or produce an explicit unsafe/degraded status.
4. Quality-gate and structural diagnostic snapshots should expose this degraded
   state so a run cannot be mistaken for a successful AI-first pass.

### 11. Keep segment detection subordinate to applied AI structure

Current risk:

- Segment detection still has typography fallback rules. The parent spec keeps
  segment detection unchanged, so this is not a blocker, but it can still
  reintroduce heuristic boundaries after Stage 3 if not clearly sourced.

Required direction:

1. Prefer AI-applied heading/structure roles when present.
2. Use typography fallback only when AI structure is absent or explicitly
   degraded.
3. Mark segment boundary evidence with source/provenance such as `ai_role`,
   `document_map`, or `typography_fallback`.

### 12. Keep follow-up docs honest about completed checklist vs open authority work

Current risk:

- Follow-up summaries can say no open implementation findings remain while the
  principle-level authority boundary still has work.

Required direction:

1. Keep mechanical checklist completion separate from architecture-hardening
   completion.
2. Link follow-up docs to this `Open Authority-Boundary Work` section.
3. When a new issue is found, classify it as one of: signal extraction, Stage 1
   map reasoning, Stage 2 anchoring, Stage 3 reconciliation, fallback/degraded
   status, or downstream authority leak.

These tasks are the current focus for future work on this spec.

## Closed Checklist

- [x] Added disabled-by-default `structure_recovery` config sections to `config.toml`.
- [x] Added flat `AppConfig` / config-loader plumbing for `structure_recovery` defaults, env overrides, and clamps.
- [x] Added stable `ParagraphUnit.logical_index` assignment in extraction identity plumbing.
- [x] Versioned prepared-document and structure-map cache keys with structure recovery mode and coordinate schema version.
- [x] Added focused config/preparation tests covering new defaults, env overrides, and logical-index-based cache-key behavior.
- [x] Added explicit structure-recovery mode plumbing from extraction into role/layout/repair helpers while preserving legacy behavior when disabled.
- [x] Made cleanup status text mode-aware so signal-only cleanup reports use `помечено`, not `удалено`.
- [x] Switched `promote_short_standalone_headings(...)` and `normalize_front_matter_display_title(...)` to hint-only behavior in `ai_first` mode.
- [x] Added `layout_cleanup` signal-only mode for `ai_first`: no paragraph removal, flag counts in report, and paragraph-level repeated/page-number flags.
- [x] Switched TOC-derived heading promotion in `structure_repair.py` to hint-only behavior in `ai_first` while preserving legacy list/TOC boundary repairs.
- [x] Projected extraction-time heuristic heading detection into advisory hints in `ai_first`, while keeping explicit headings authoritative.
- [x] Switched adjacent caption reclassification to advisory `caption` hints in `ai_first` while preserving asset attachment side effects.
- [x] Added advisory structural-role hints and switched bounded TOC region marking to signal-only behavior in `ai_first`.
- [x] Switched compound TOC split-generated `toc_entry` pieces to advisory structural-role hints in `ai_first`.
- [x] Switched compound TOC split-generated `list` and non-body structural pieces to advisory hints in `ai_first`.
- [x] Switched `structure_repair` list-merge branches to signal-only list hints in `ai_first` instead of merging paragraphs.
- [x] Preserved paragraph topology for compound TOC splitting in `ai_first` by storing embedded structure hints on the original paragraph.
- [x] Added Stage 1 `DocumentMap*` dataclasses plus document-map cache-key scaffolding in preparation.
- [x] Added deterministic Stage 1 document-map descriptor/sampling helpers and a public `build_document_map(...)` fallback scaffold.
- [x] Wired the Stage 1 document-map scaffold into preparation behind `structure_recovery.document_map.enabled`, storing `PreparedDocumentData.document_map` without changing downstream classification yet.
- [x] Added Stage 1 in-memory document-map cache reuse in preparation using the document-map cache key and stage tag.
- [x] Added `.run/document_maps/<cache_key>.json` debug artifact writing with sampled indexes, prompt/schema version metadata, and full `DocumentMap` payload.
- [x] Wired Stage 1 runtime to `structure_recovery.document_map.preview_chars` and `max_input_tokens`, so descriptor previews and deterministic sampling now honor the configured input budget.
- [x] Added a real Stage 1 AI `DocumentMap` path with `prompts/document_map_system.txt`, schema validation, sparse-anchor default filling, and a one-shot retry on schema-invalid model output before deterministic fallback.
- [x] Persisted terminal schema-invalid Stage 1 model outputs as malformed document-map artifacts for postmortem auditing instead of dropping them silently during fallback.
- [x] Aligned terminal Stage 1 AI/schema failure handling with the spec so preparation now falls back to `document_map=None` and the legacy non-anchored Stage 2 path instead of silently injecting a synthetic low-confidence map.
- [x] Added Stage 2 anchor scaffolding on `ParagraphDescriptor` and `build_paragraph_descriptors(...)`, including `anchor_r` / `anchor_l` / `anchor_c` prompt payload fields.
- [x] Extended structure-recognition prompt guidance with anchor consistency rules for high/medium/low confidence document-map anchors.
- [x] Passed `document_map` through preparation into `build_structure_map(...)` and included anchor fingerprints in the structure-map cache key.
- [x] Switched anchored structure recognition from pure count-based windowing to deterministic token-budgeted window shrinking using `structure_recovery.anchored_classification.target_input_tokens`.
- [x] Propagated anchored `target_input_tokens` into `build_structure_map(...)` while preserving the legacy non-anchored windowing path when `document_map` is absent.
- [x] Enforced deterministic document-map anchor guards during `apply_structure_map(...)` and switched anchored apply-thresholds to `structure_recovery.anchored_classification.min_confidence`.
- [x] Added explicit structure-recognition prompt/schema versioning to structure-map cache keys and debug artifacts so prompt-only behavior changes bust stale cache entries.
- [x] Added a minimal Stage 3 deterministic reconciliation pass that projects high-confidence document-map anchors back into `StructureMap`, reports outline/TOC mismatches, and runs before final Stage 2 apply.
- [x] Added a bounded Stage 3 targeted reconciliation recall path that triggers only above the configured divergence threshold, reclassifies only the flagged subset plus local neighbours, and persists a reconciliation report artifact.
- [x] Added post-AI structure validation after final Stage 3 apply, including advisory `document_map_present` and `outline_coverage_ratio` fields in the persisted validation report while preserving the pre-AI diagnostic gate for auto escalation.
- [x] Realized Stage 1 `vertical_gap_before_pt` from stored paragraph properties XML and promoted high-gap paragraphs into DocumentMap sampling instead of hardcoding `gap=null`.
- [x] Relaxed Stage 2 high-anchor apply guards so they no longer blanket-block every mismatch; only medium-confidence overrides on clearly prose-like or clearly heading-like local text are allowed.
- [x] Aligned anchored Stage 2 token budgeting with the spec: the implementation now shrinks descriptor preview length before reducing window size when a window exceeds `target_input_tokens`.
- [x] Refocused the spec's testing strategy onto a single structure-scoped canonical document: `lietaer-pdf-first-20-structure-core` as the default PDF loop, structural diagnostics by default, and full-tier runs only as rare late checkpoints.
- [x] Restored a working default model path for structural diagnostics; the current canonical contract is that unresolved structural stages inherit the repository text default unless explicitly overridden.
- [x] Fixed Stage 2 timeout recovery so local `StructureRecognitionRequestTimeout` failures split oversized windows instead of being swallowed into empty `StructureMap` no-ops; the canonical first-20-pages structural diagnostic now completes with non-zero AI classifications.
- [x] Started Slice 5 heuristic deprecation by removing physical list-fragment topology merging from `document/structure_repair.py`; isolated markers and split list leads now stay as original paragraphs with advisory list hints instead of being rewritten before AI structure classification.
- [x] Continued Slice 5 in `document/structure_repair.py` by converting remaining heading/list role mutations to advisory hints while preserving TOC-region binding and compound-split topology; TOC-aligned heading/list candidates no longer bind `role`/`heading_source` directly before AI classification.
- [x] Added validation-side support for `heuristic_structural_role_hint` and heading hints in `structure/validation.py`, so bounded TOC/front-matter readiness checks continue to work as `structure_repair.py` mutating branches are removed; the canonical first-20-pages structural diagnostic returned to `quality_gate_status = pass` after this support fix.
- [x] Added TOC-hint support in `document/relations.py`, `document/semantic_blocks.py`, and `document/segments.py`, so downstream TOC grouping, TOC-region relations, and segment diagnostics now read `heuristic_structural_role_hint` instead of depending on bound `structural_role` from legacy repair code.
- [x] Continued Slice 5 by removing bounded TOC role binding from `document/structure_repair.py`; bounded TOC detection is now advisory-hint-only, focused repair/block/segment tests stayed green, and the canonical first-20-pages structural diagnostic still returned `passed = true` with `quality_gate_status = pass`.
- [x] Removed the remaining physical compound TOC split branch from `document/structure_repair.py`; compound TOC-aligned paragraphs now always preserve original topology and carry embedded advisory structure hints instead of rewriting the paragraph list even on the legacy path.
- [x] Projected `heuristic_embedded_structure_hints` into Stage 1 document-map and Stage 2 structure-recognition descriptor payloads, bumped prompt/schema versions, and prioritized embedded-hint paragraphs in document-map sampling so compound split signals now reach the AI path instead of only cache/debug artifacts.
- [x] Taught `document/semantic_blocks.py` and `build_editing_jobs(...)` to consume embedded compound-structure hints: mixed compound paragraphs now isolate at block boundaries, and TOC passthrough no longer misclassifies paragraphs whose embedded hints mix TOC with heading/body content.
- [x] Removed the remaining mutation routing from `document/layout_cleanup.py`; layout cleanup now runs as flag-only signal extraction for all modes, and focused cleanup/extraction regressions were updated to stop expecting paragraph deletion from page-number or repeated-artifact detection.
- [x] Closed the remaining Stage 0 front-matter normalization leak in `document/roles.py`: AI-first cover-title normalization no longer demotes sibling heading paragraphs back to body during metadata cleanup, so this pre-AI slice is now signal-only there as well.
- [x] Propagated flag-only layout-cleanup signals through preparation summaries, UI summary flatteners, and structural validation metrics, while keeping the existing public metric keys stable; cleanup evidence is no longer dropped as zeros outside the cleanup module itself.
- [x] Aligned the canonical first-20-pages proof path with the spec contract: the structural diagnostic snapshot now exposes `document_map_present`, `outline_coverage_ratio`, `front_matter_leaks`, and `targeted_recall_invoked`, and repo defaults now enable AI-first structure recovery plus Stage 1 document-map generation for the ordinary canonical loop.
- [x] Hardened the canonical first-20-pages coverage path against Stage 1 outline noise and Stage 1/2 off-by-one heading drift: TOC-local outline entries are now sanitized out of parsed document maps, document-map cache/debug metadata is versioned with a Stage 1 postprocess version, and reconciliation accepts a same-level heading match within one adjacent logical paragraph. The canonical structural diagnostic for `lietaer-pdf-first-20-structure-core` now returns `outline_coverage_ratio = 1.0` and `quality_gate_status = pass` again.
- [x] Clarified the proof boundary after the latest live rerun: if the separate non-canonical full `lietaer-core` runtime emits `quality_gate_status = warning` with `structure_recognition_noop_on_high_risk`, treat that as an advisory runtime signal on that full-run path, not as a reopened structural-regression or remaining-work signal for the canonical `lietaer-pdf-first-20-structure-core` diagnostic contract.
