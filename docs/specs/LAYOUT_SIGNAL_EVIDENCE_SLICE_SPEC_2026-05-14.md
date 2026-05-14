# Layout Signal Evidence Slice Spec

Date: 2026-05-14
Status: Proposed
Parent spec: `docs/specs/TOPOLOGY_FIRST_STRUCTURE_RECOVERY_REMEDIATION_SPEC_2026-05-12.md`
Authority position: **Slice between Phase 1 and Phase 2** of the parent spec. Does
not change Variant A authority discipline. Adds new `evidence` tags only.

## TL;DR

Stage 1.5 currently decides `merge_heading_continuation` membership only from
text-token compatibility against the Stage 1 `DocumentMap` canonical title.
We have richer per-paragraph signals already attached to `ParagraphUnit`
(font size, font cluster, optional page-number hints, vertical gap, repeated-
across-pages flag) that are not consulted in that decision. This slice plugs
those existing signals into the **evidence layer** of Stage 1.5 so that:

- Continuation members can be accepted when token-prefix matching alone is
  insufficient but Stage 1 authority already preserves the full canonical title
  or explicit member bounds from Phase 1b, and local font/style signals confirm
  that those paragraphs belong to one heading unit.
- Page-artifact + heading concatenations can become candidate diagnostics (not
  binding splits) from page-furniture phrase detection plus local heading
  neighborhood, with page-boundary evidence emitted only when trustworthy page
  hints are actually present.
- Stage 2 and Slice 1 topology-precedence consumers continue to rely on the
  existing projected-unit surfaces (`unit_id`, `unit_heading_level`,
  `authority`). No descriptor schema change is introduced by this slice.

No new runtime dependencies. No PDF backend change. No GPL/AGPL code lifted.
All paragraph-level inputs already exist in `core/models.py` `ParagraphUnit`.

## Source Attribution

The algorithms are clean-room reimplementations of well-known patterns. Sources
are listed for traceability; **no code is copied**.

| Pattern | Reference project | License of reference | Status |
| --- | --- | --- | --- |
| Body-font baseline as mode of body paragraphs | `unstructured.io` partitioners | Apache-2.0 | Pattern only |
| Heading clusters as font-size buckets above baseline | `marker` `marker/processors/sectionheader.py` style | GPL-3.0 (code) | Pattern only |
| Section hierarchy via descending font sizes | `marker` `marker/builders/structure.py` style | GPL-3.0 (code) | Pattern only |
| Page-artifact phrase library | generic OCR/PDF pipelines | n/a | Pattern only |
| Multi-line heading grouping by visual proximity | `pdfplumber`-based pipelines, `papermage` Entity model | MIT, Apache-2.0 | Pattern only |
| `unit_type` vocabulary alignment | `marker` JSON output and `surya` layout labels | GPL-3.0 (code) | Naming alignment only |

Specifically, we do not copy any source file from those projects. We do not
add any of them as a runtime or build dependency. We use them only as
references for algorithm shape.

## Non-Goals For This Slice

- No new Python dependencies (no `pdfplumber`, no `pypdfium2`, no `PyMuPDF` in
  `requirements.txt`).
- No replacement of the LibreOffice `writer_pdf_import` PDF path.
- No bbox-based layout (we do not have bbox in production runtime).
- No reading-order recomputation (XYCut, etc.). Reading order remains the order
  produced by LibreOffice → python-docx.
- No change to Stage 1 `DocumentMap` prompt or schema. Stage 1 prompt slice is
  separate (see Phase 1b in the parent spec). This slice assumes Phase 1b is
  already active whenever late-book composite chapter titles require full-title
  or explicit-member authority.
- No projection-side recovery of text or membership beyond Stage 1 authority.
  If Stage 1 emits a truncated title or incomplete member boundary, this slice
  must fail closed rather than synthesize the missing suffix from layout alone.
- No new binding split path. `split_page_artifact_from_heading` remains gated
  by `DocumentMapSplitHint` per Variant A. This slice only adds **candidate-
  only** diagnostics for page-artifact detection.
- No new per-paragraph physical page-coordinate extraction. Current
  `page_number` semantics are treated as optional hints, not as a universal
  page-boundary oracle.
- No change to `ParagraphUnit` schema. All required fields already exist.

If at a later stage bbox-level signals are required, that is a separate spec
that would justify adding `pdfplumber` (MIT) as a single new dependency.

## Verified Current-State Evidence

### Signals Already Present On `ParagraphUnit`

`src/docxaicorrector/core/models.py` `ParagraphUnit` already carries:

- `font_size_pt: float | None`
- `font_size_z_score: float | None`
- `style_cluster_id: int | None`
- `vertical_gap_before_pt: float | None`
- `page_number: int | None` (sparse page-number hint, not a reliable physical
  page coordinate for every paragraph)
- `is_repeated_across_pages: bool`
- `is_likely_page_number: bool`
- `heading_level: int | None` together with `heading_source: str | None`
  (explicit DOCX heading style is represented as `heading_source == "explicit"`)
- `heuristic_heading_level_hint: int | None`
- `is_bold: bool`, `is_italic: bool`
- `style_name: str`

These are populated by the existing extraction pipeline. No change is needed
to the extraction layer for this slice.

### Decision Gates That Currently Ignore Layout Signals

In `src/docxaicorrector/structure/topology.py`:

- `_is_heading_continuation_candidate(paragraph, paragraph_text)` applies only
  lexical/shape guards (`is_repeated_across_pages`, `is_likely_page_number`,
  max-length / max-word-count / alphabetic / trailing-period filters). It does
  not consult font cluster, style cluster, vertical gap, or observed page
  boundaries.
- `_build_heading_continuation_unit(...)` walks forward up to
  `_HEADING_CONTINUATION_WINDOW = 3` paragraphs and accepts a continuation only
  if `_token_sequences_compatible(candidate_tokens, canonical_tokens)` returns
  true. When `canonical_tokens` come from a truncated `DocumentMap.outline.title`
  (e.g., `"Governance and We"` with no `the Citizens: An Ancient Future?`), the
  match fails for every continuation member, and the function emits **no merged
  unit** because a one-member collection is rejected.

This is the failure mode that the upstream chapter-region diagnostic exhibits
on the Lietaer Chapter 11 case. In the current code, the token check is the
only membership gate; this slice broadens the evidence layer only when Stage 1
authority is already sufficient.

### Page Boundary Hints And Page-Artifact Phrases

The current `page_number` field on `ParagraphUnit` is not a generalized
per-paragraph page locator; in the current extraction path it behaves mainly as
an optional page-number hint. This means page-boundary corroboration is **not**
universally observable today. For this slice, candidate page-artifact
diagnostics must rely primarily on a closed page-furniture phrase library plus
local authoritative-heading neighborhood. A `page_break_boundary` evidence tag
may be attached only when trustworthy page-hint transitions are actually
present.

## Architectural Position

This slice is purely additive in Stage 1.5:

```text
DocumentMap (Stage 1)
  -> layout_signals = derive_layout_signals(paragraphs)         # NEW, pure
  -> projection = apply_document_map_topology(
        paragraphs, document_map,
        layout_signals=layout_signals,                          # NEW
        app_config=...,
     )
        # Inside projection:
        # - _is_heading_continuation_candidate consults font/style evidence
        # - _build_heading_continuation_unit can confirm Stage 1-bounded members
        # - candidate page-artifact diagnostics are recorded
```

Stage 1.5 still uses Stage 1 authority. The widening rule is: **a continuation
member is accepted only inside the Stage 1 authority envelope**. Concretely,
the projection may use layout evidence to validate or reject candidate members
already bounded by Stage 1 canonical text and/or explicit Stage 1
`member_logical_indexes` from Phase 1b. The widening path must not invent a new
authority value, new member boundary, or new canonical suffix. `authority`
remains `document_map_outline` or `document_map_toc`, and the new path is
recorded in `evidence` only.

This preserves Variant A: text-token logic remains a validator, layout signals
remain evidence enrichers, and missing Stage 1 title/membership authority is
still a Stage 1 failure rather than a projection concern.

## Data Model Additions

### New module: `src/docxaicorrector/structure/layout_signals.py`

Pure-Python, no I/O, no AI calls. Computes per-document layout context once
and produces a sidecar object that Stage 1.5 reads by `logical_index`.

```python
from dataclasses import dataclass

LAYOUT_SIGNALS_SCHEMA_VERSION = 1

@dataclass(frozen=True)
class FontClusterTier:
    """One tier in the font-size hierarchy of the document."""
    tier_id: int                # 0 == body baseline, 1 = first above-baseline tier, ...
    representative_pt: float    # midpoint of the tier
    member_logical_indexes: tuple[int, ...]
    is_body_baseline: bool
    is_heading_candidate: bool  # representative_pt >= baseline * heading_ratio

@dataclass(frozen=True)
class LayoutSignalsRecord:
    """Per-paragraph layout-derived signals, keyed by logical_index."""
    logical_index: int
    tier_id: int
    is_heading_tier: bool
    is_body_tier: bool
    font_size_pt: float | None
    page_number: int | None      # optional page hint; absent for many paragraphs
    vertical_gap_before_pt: float | None
    is_first_on_page: bool       # true only for observed page-hint transitions
    is_short_line: bool          # text length <= SHORT_LINE_CHARS
    is_above_baseline: bool      # font_size_pt > baseline_pt + baseline_tolerance_pt

@dataclass(frozen=True)
class LayoutSignals:
    schema_version: int
    body_baseline_pt: float | None
    body_baseline_tolerance_pt: float
    heading_ratio: float                 # default 1.15
    tiers: tuple[FontClusterTier, ...]
    records_by_logical_index: dict[int, LayoutSignalsRecord]

    def get(self, logical_index: int) -> LayoutSignalsRecord | None: ...
    def is_same_heading_tier(self, a: int, b: int) -> bool: ...
    def is_page_break_between(self, a: int, b: int) -> bool: ...
```

### Extended `VALID_TOPOLOGY_EVIDENCE` In `topology.py`

Add three closed-vocabulary evidence tags:

```python
VALID_TOPOLOGY_EVIDENCE = frozenset(
    {
        # existing ...
        "outline_entry",
        "toc_entry",
        "split_hint",
        "adjacent_short_heading_fragments",
        "local_heading_neighborhood",
        "bounded_toc_region",
        "page_artifact_phrase",
        "one_to_one_toc_entry_match",
        # added by this slice:
        "font_cluster_match",
        "page_break_boundary",
        "body_font_baseline_outlier",
    }
)
```

Vocabulary semantics:

- `font_cluster_match`: continuation member's `FontClusterTier.tier_id` equals
  the heading anchor's tier_id and that tier is a heading tier.
- `page_break_boundary`: the candidate page artifact split is additionally
  corroborated by an **observed** page-hint transition in the local window.
  This evidence is opportunistic only; its absence does not block the candidate
  diagnostic, and it never becomes binding without Stage 1 hint authority.
- `body_font_baseline_outlier`: paragraph's `font_size_pt` is detectable as
  body baseline outlier (used for low-confidence diagnostics, not binding).

Adding these requires bumping `TOPOLOGY_PROJECTION_SCHEMA_VERSION` from `1`
to `2` (see Cache Key & Schema below).

### Closed Vocabularies Touched Elsewhere

No new `unit_type` values. No new `authority` values. Only `evidence` grows.
Adding to `VALID_TOPOLOGY_AUTHORITIES` or `VALID_TOPOLOGY_UNIT_TYPES` is
explicitly out of scope for this slice.

## Algorithms

All algorithms are O(N) over paragraphs and run synchronously during Stage 1.5.

### Body Baseline And Font Tiers

Inputs: `list[ParagraphUnit]` after structure-recovery preparation completes.

```python
def derive_layout_signals(
    paragraphs: Sequence[ParagraphUnit],
    *,
    heading_ratio: float = 1.15,
    short_line_chars: int = 80,
    baseline_tolerance_pt: float = 0.25,
    min_tier_population: int = 2,
) -> LayoutSignals:
    ...
```

Algorithm:

1. Collect `font_size_pt` from every `ParagraphUnit` where:
   - `role != "image"` and `role != "table"`;
   - `is_likely_page_number is False`;
   - `is_repeated_across_pages is False`;
   - `font_size_pt is not None and font_size_pt > 0`.
   If fewer than 8 qualifying paragraphs exist, return a `LayoutSignals`
   with `body_baseline_pt = None`, an empty tiers tuple, and
   per-paragraph records whose `is_heading_tier=False`, `is_body_tier=False`.
   This slice is feature-degraded but not failing.
2. Compute the mode of `round(font_size_pt, 1)` across the qualifying set as
   `body_baseline_pt`. If a tie occurs, prefer the smallest value (body text
   is typically the smallest non-footnote tier in narrative books).
3. Bucket all paragraphs by `round(font_size_pt, 1)`:
   - tier 0 ≡ body baseline (within `± baseline_tolerance_pt`);
   - tiers 1..K ≡ unique values strictly above `body_baseline_pt + baseline_tolerance_pt`,
     ordered descending (largest font is tier 1).
   - Discard tiers with `len(members) < min_tier_population` unless they are
     the largest font size in the document (they may legitimately host the
     title only); preserve them as `is_heading_candidate=True` regardless.
4. `is_heading_tier := representative_pt >= body_baseline_pt * heading_ratio`
   when `body_baseline_pt is not None`, otherwise `False`.
5. For each paragraph, fill `LayoutSignalsRecord`:
   - `tier_id` via the buckets above; missing `font_size_pt` → `tier_id = -1`
     and both `is_heading_tier=False, is_body_tier=False`.
   - `is_short_line := len(text.strip()) <= short_line_chars`.
    - `is_first_on_page := previous paragraph's page_number is not None and
      this page_number is not None and previous page_number != this page_number`.
      This is an observed page-hint transition only and may remain `False` for
      most paragraphs in current production extraction.
    - `is_above_baseline := font_size_pt > body_baseline_pt + baseline_tolerance_pt`.

`heading_ratio = 1.15` is the conservative default from `unstructured.io`-style
font-rule pipelines. It tolerates `12pt body + 14pt heading` while rejecting
`11pt body + 12pt emphasized inline`.

### Continuation Widening Inside `_is_heading_continuation_candidate`

Updated signature:

```python
def _is_heading_continuation_candidate(
    paragraph: ParagraphUnit,
    paragraph_text: str,
    *,
    layout_signals: LayoutSignals | None = None,
    anchor_logical_index: int | None = None,
) -> tuple[bool, tuple[str, ...]]:
    ...
```

Return changes from `bool` to `tuple[bool, tuple[str, ...]]` where the second
element is the **evidence tags** the continuation acceptance produced. Caller
appends them to the unit's `evidence` field, deduplicated, in stable order.

Acceptance rules, evaluated in order:

1. **Existing hard/lexical guards stay in force**: keep today's reject rules
   for repeated-across-pages, likely page numbers, overlong fragments,
   non-alphabetic fragments, and fragments ending with a period. This slice
   layers layout evidence on top of those guards; it does not remove them.
2. **Token-prefix path**: if `_token_sequences_compatible(...)` succeeds
   against the Stage 1 canonical heading tokens, return
   `(True, ("adjacent_short_heading_fragments",))`. Unchanged.
3. **Layout confirmation path** (new, authority-bounded):
   - require `layout_signals is not None` and `anchor_logical_index is not None`;
   - require the Stage 1 target already bounds this candidate via explicit
     `member_logical_indexes` or equivalent Phase 1b authority metadata;
   - require `layout_signals.is_same_heading_tier(anchor_logical_index, paragraph.logical_index)`;
   - require `paragraph_record.is_short_line` is True;
   - if `layout_signals.is_page_break_between(anchor_logical_index, paragraph.logical_index)`
     is `True`, reject;
   - require `paragraph.style_cluster_id is None or paragraph.style_cluster_id == anchor.style_cluster_id` (i.e., not crossing into a different visual style);
   - if all checks hold, return
     `(True, ("adjacent_short_heading_fragments", "font_cluster_match"))`.
4. **Default**: `(False, ())`.

This is **not** a durable fix for a truncated-title Stage 1 map. If Stage 1
still emits `"Governance and We"` without the subtitle or without explicit
member bounds from Phase 1b, this slice must not recover `the Citizens` /
`An Ancient Future?` from layout alone. The durable fix for that case remains
Phase 1b authority.

### Canonical Text Coverage Invariant Compliance

The parent spec mandates that `StructuralUnit.canonical_text` cover the text of
every member `logical_index`. Because this slice does **not** extend Stage 1
authority, the widening path must not synthesize canonical text by appending
physical paragraph text outside the Stage 1 title.

Update `_build_heading_continuation_unit(...)` so that layout-confirmed members
are emitted only when the Stage 1 target already provides a `canonical_text`
that covers all authorized members (for example, because Phase 1b preserved the
full title or because explicit member indexes are paired with a full canonical
title). If that invariant is not met, fail closed and emit no widened unit.

This keeps the invariant honest without turning layout evidence into a hidden
authority-extension path.

### Page-Artifact Candidate Diagnostic

Pure diagnostic. No binding split. No mutation of `paragraphs`. Emitted into
the `DocumentTopologyProjection.operations` tuple as an `op` value that
existing consumers treat as advisory.

Algorithm:

1. Define a small **closed phrase library** (`_PAGE_FURNITURE_PHRASES`) of
   normalized, lower-cased prefixes that historically concatenate with chapter
   headings. Initial entries:
   - `"this page intentionally left blank"`;
   - `"эта страница намеренно оставлена пустой"`;
   - `"page intentionally left blank"`;
   - `"intentionally blank"`;
   - `"intentionally left blank"`.
   The library is closed: adding entries requires updating the spec AND a
   round-trip test that verifies the new entry's behavior.
2. For each paragraph `P`:
   - lowercase normalize `P.text`;
   - if any phrase from the library is a prefix substring within the first
      120 characters AND the paragraph text length exceeds the phrase length
      by at least 6 characters (i.e., something follows it) AND
      `_find_local_heading_target(...)` returns a non-None local heading target
      for `P` or `P+1`:
    - emit a `DocumentTopologyOperation` with:
      - `op = "candidate_page_artifact_split"` (new candidate-only op kind,
        allowlisted but not bound);
      - `authority = "document_map_outline"` or `"document_map_toc"` depending
        on the matched target;
      - `confidence = "candidate"`;
      - `evidence = ("page_artifact_phrase", "local_heading_neighborhood")`,
        plus `"page_break_boundary"` only if the local window also shows an
        observed page-hint transition.
3. The candidate operation does **not** create a `StructuralUnit`. It is a
   diagnostic that subsequent phases (Phase 3 binding split) can promote into
   a binding split once Stage 1 emits the corresponding `DocumentMapSplitHint`.
4. Quality gates and Stage 2 descriptors do **not** consume
   `candidate_page_artifact_split`. It is observability only.

This step provides the cheap, honest visibility into "we see it, we cannot
fix it yet without Stage 1 authority", replacing the markdown-side
`normalize_page_placeholder_heading_concats_markdown` as the source of truth
for that defect.

### `op` Vocabulary Extension

The `DocumentTopologyOperation.op` field is currently not validated against a
closed vocabulary in the dataclass itself. This slice formalizes the closed
set in `topology.py` as a module-level constant and validates inside
`apply_document_map_topology(...)` via a dedicated helper (for example,
`_validate_projection_vocabularies(...)`) that checks every emitted operation's
`op` and `evidence`, and every emitted unit's `unit_type` / `authority` /
`evidence`, raising `ValueError` on an out-of-vocabulary value:

```python
VALID_TOPOLOGY_OPERATIONS = frozenset(
    {
        # existing:
        "merge_heading_continuation",
        "split_page_artifact_from_heading",
        "split_compound_toc_entries",
        # added by this slice:
        "candidate_page_artifact_split",
    }
)
```

Adding a new value requires the same schema-version bump and round-trip test
discipline as the existing closed vocabularies.

## Integration Surfaces

### File: `src/docxaicorrector/structure/layout_signals.py` (new)

Create with:

- `LAYOUT_SIGNALS_SCHEMA_VERSION = 1` constant.
- Frozen dataclasses `FontClusterTier`, `LayoutSignalsRecord`, `LayoutSignals`.
- Pure function `derive_layout_signals(paragraphs, *, heading_ratio=1.15, short_line_chars=80, baseline_tolerance_pt=0.25, min_tier_population=2) -> LayoutSignals`.
- Module is import-free of `core.models`-level dataclasses except `ParagraphUnit`
  (which it imports from `core.models`).
- No I/O, no logging at module level. Module is safe to import at startup.
- Type-checked under existing pyright settings.

### File: `src/docxaicorrector/structure/topology.py`

Changes:

1. Import `LayoutSignals, derive_layout_signals, LAYOUT_SIGNALS_SCHEMA_VERSION`
   from `.layout_signals`.
2. Bump `TOPOLOGY_PROJECTION_SCHEMA_VERSION` from `1` to `2`.
3. Extend `VALID_TOPOLOGY_EVIDENCE` with the three new tags.
4. Add `VALID_TOPOLOGY_OPERATIONS` constant and validate in
   `apply_document_map_topology(...)` (already at construction site).
5. Extend `apply_document_map_topology(...)` signature:

```python
def apply_document_map_topology(
    paragraphs: list[ParagraphUnit],
    document_map: DocumentMap,
    *,
    app_config: Mapping[str, Any],
    document_map_cache_key: str | None = None,
    layout_signals: LayoutSignals | None = None,
) -> DocumentTopologyProjection:
    ...
```

When `layout_signals is None`, behavior must remain semantically compatible
with the existing implementation (only token-prefix path; no candidate
page-artifact diagnostics). When the caller passes `layout_signals`, the
evidence-enrichment path becomes active.

6. Update `_is_heading_continuation_candidate(...)` signature and behavior as
   defined in **Continuation Widening Inside `_is_heading_continuation_candidate`**.
7. Update `_build_heading_continuation_unit(...)` to:
   - accept `layout_signals` and the heading anchor's `logical_index`;
   - thread evidence tags returned by `_is_heading_continuation_candidate(...)`
     into the unit's `evidence` field (deduplicated, stable order);
   - fail closed if Stage 1 `canonical_text` does not already cover all
     authority-bounded members.
8. Add `_emit_candidate_page_artifact_operations(...)` as defined above.
9. Update `build_document_topology_projection_cache_key(...)` payload:
   - add `layout_signals_schema_version` field;
   - add `layout_signals_fingerprint` field that summarizes the body baseline
     and tier representatives. Suggested payload:
     `{"body_baseline_pt": ..., "tiers": [{"tier_id": ..., "pt": ...}, ...]}`.
   - Include this fingerprint only when `layout_signals is not None`.
   - Because this slice bumps `TOPOLOGY_PROJECTION_SCHEMA_VERSION`, existing
     topology artifacts and cache keys are expected to invalidate once the
     slice lands. Disabled-path compatibility requirement is therefore
     **semantic**, not byte-identical: units/operations must match today's
     behavior when the flag is off.

### File: `src/docxaicorrector/processing/preparation.py`

Find the existing call site of `apply_document_map_topology(...)`. Wire
`layout_signals` through:

```python
layout_signals = (
    derive_layout_signals(paragraphs)
    if bool(app_config.get("structure_recovery_topology_projection_layout_signals_enabled", False))
    else None
)
topology_projection = apply_document_map_topology(
    paragraphs,
    document_map,
    app_config=app_config,
    document_map_cache_key=document_map_cache_key,
    layout_signals=layout_signals,
)
```

`structure_recovery_topology_projection_layout_signals_enabled` is the slice's feature
flag. Default `False` until acceptance tests pass.

When `layout_signals is not None`, emit a new event
`document_topology_layout_signals_built` carrying:

- `body_baseline_pt`;
- `tier_count`;
- `heading_tier_count`;
- `paragraphs_with_font_size_count`;
- `heading_ratio`.

The event is observability only. It is part of the existing event log and is
covered by `docs/LOGGING_AND_ARTIFACT_RETENTION.md` retention defaults.

### File: `src/docxaicorrector/validation/structural.py`

Update the topology-projection snapshot fallback path so it threads
`layout_signals` through `apply_document_map_topology(...)` under the same
feature flag. This keeps structural diagnostic snapshots from silently using a
different projection path than the preparation pipeline.

### File: `src/docxaicorrector/core/models.py`

No schema changes for `ParagraphUnit`, `StructuralUnit`,
`DocumentTopologyOperation`, or `DocumentTopologyProjection`.

The only model-level change is the extended closed vocabulary set in
`structure/topology.py`, which is a `frozenset` constant validated at
construction time and serialized through evidence-tuple fields that already
round-trip.

### File: `src/docxaicorrector/core/config_structure_sections.py`

Add config keys under the existing `[structure_recovery.topology_projection]`
section using the repository's current flattening pattern:

```toml
[structure_recovery.topology_projection]
layout_signals_enabled = false
layout_signals_heading_ratio = 1.15
layout_signals_short_line_chars = 80
layout_signals_baseline_tolerance_pt = 0.25
layout_signals_min_tier_population = 2
```

Corresponding env overrides:

- `DOCX_AI_STRUCTURE_RECOVERY_TOPOLOGY_LAYOUT_SIGNALS_ENABLED`
- `DOCX_AI_STRUCTURE_RECOVERY_TOPOLOGY_LAYOUT_SIGNALS_HEADING_RATIO`
- `DOCX_AI_STRUCTURE_RECOVERY_TOPOLOGY_LAYOUT_SIGNALS_SHORT_LINE_CHARS`
- `DOCX_AI_STRUCTURE_RECOVERY_TOPOLOGY_LAYOUT_SIGNALS_BASELINE_TOLERANCE_PT`
- `DOCX_AI_STRUCTURE_RECOVERY_TOPOLOGY_LAYOUT_SIGNALS_MIN_TIER_POPULATION`

Clamping:

- `heading_ratio` clamped to `[1.05, 2.0]`;
- `short_line_chars` clamped to `[20, 400]`;
- `baseline_tolerance_pt` clamped to `[0.0, 2.0]`;
- `min_tier_population` clamped to `[1, 100]`.

Flattened app-config keys must follow the same naming convention:

- `structure_recovery_topology_projection_layout_signals_enabled`
- `structure_recovery_topology_projection_layout_signals_heading_ratio`
- `structure_recovery_topology_projection_layout_signals_short_line_chars`
- `structure_recovery_topology_projection_layout_signals_baseline_tolerance_pt`
- `structure_recovery_topology_projection_layout_signals_min_tier_population`

These follow the existing config-loader clamp pattern.

### File: `src/docxaicorrector/structure/recognition.py`

No signature change required for this slice. The Slice 1 topology precedence
guard from the parent spec already consumes `topology_projection` and uses
unit `unit_type` / `heading_level` / `authority`. The new evidence tags are
not consulted by the guard. The guard remains independent.

A follow-up may consider whether `topology_authority_protected_count` should
distinguish units whose acceptance evidence includes `font_cluster_match` from
those backed purely by `outline_entry`. That is observability sugar and is
out of scope for this slice.

### File: `src/docxaicorrector/structure/document_map.py`

No change. Stage 1 prompt is not modified. `DocumentMap` cache fingerprint is
not bumped. This slice's schema bump is `TOPOLOGY_PROJECTION_SCHEMA_VERSION`,
which already participates in the topology projection cache key, not in the
Stage 1 `DocumentMap` cache key.

## Cache Key And Schema

### Bumped Fields

- `TOPOLOGY_PROJECTION_SCHEMA_VERSION`: `1 -> 2`.
- `LAYOUT_SIGNALS_SCHEMA_VERSION`: new constant, starts at `1`.
- Existing topology cache artifacts are expected to invalidate at rollout
  because the projection schema changes. This is acceptable and should be
  treated as an intentional one-time cache turnover.

### Payload Fingerprint For `layout_signals_fingerprint`

```json
{
  "schema_version": 1,
  "body_baseline_pt": 11.5,
  "heading_ratio": 1.15,
  "tiers": [
    {"tier_id": 1, "pt": 18.0, "is_heading_candidate": true},
    {"tier_id": 2, "pt": 14.0, "is_heading_candidate": true},
    {"tier_id": 0, "pt": 11.5, "is_heading_candidate": false}
  ]
}
```

When `layout_signals is None`, this key is **absent** from the payload, not
present-with-null. This keeps the disabled-path payload minimal, but the
overall cache key is still expected to change because the projection schema
version is bumped by this slice.

### Artifact Retention

`.run/document_topology/<cache_key>.json` retention is unchanged from the
parent spec: TTL 30 days, max 200 files, via
`runtime_artifact_retention.prune_artifact_dir(...)`. No new artifact
directory is introduced by this slice.

`.run/layout_signals/` is **not** introduced as a separate artifact. The
`layout_signals_fingerprint` is embedded in the topology projection cache key
payload only. If a debug artifact is later needed, it is a follow-up.

## Stage 2 Descriptor Interaction

`ParagraphDescriptor` already serializes `pt` (font_size_pt) and `hl`
(derived from `heading_level` when the paragraph carries explicit heading
authority). The widening path of Stage 1.5 will produce
`StructuralUnit` membership for paragraphs that previously appeared as
standalone descriptors. Through the existing `unit_id`/`unit_heading_level`
fields on `ParagraphDescriptor`, Stage 2 already sees them as members of one
unit.

No descriptor schema change is required for this slice. The `pt` field is
already exposed. If Stage 2 wants to consult tier id explicitly, that is a
follow-up; the current evidence trail through `unit_id` is sufficient for the
slice's acceptance.

## Reconciliation Interaction

`reconcile_with_document_map(...)` already accepts a `topology_projection`
parameter (per the parent spec). The widening rule changes only the
**membership** of existing heading units. It does not change the rule for
outline coverage:

> An outline entry is covered iff its `logical_index` is a member of a
> projected unit of `unit_type in {"chapter_heading", "section_heading"}`.

This rule is unchanged. The slice does not introduce a new reconciliation
contract.

## Quality Gate Interaction

`candidate_page_artifact_split` is **explicitly excluded** from quality gates
in `validation/structural.py`. The gate code must check `op` against the
closed set of binding operations:

```python
_BINDING_OPERATIONS = frozenset(
    {
        "merge_heading_continuation",
        "split_page_artifact_from_heading",
        "split_compound_toc_entries",
    }
)
```

`candidate_page_artifact_split` and any future candidate-only op kind must
not be included in `_BINDING_OPERATIONS`. The structure-aware
`has_toc_body_concat_structure(...)` from the parent spec already operates on
`StructuralUnit` membership, not on the `operations` tuple, so it is unaffected.

## Implementation Plan

The slice is delivered in three commits. Each commit is independently
mergeable. The flag stays `False` until the acceptance commit.

### Commit 1: Pure Module And Dataclasses

Files:

- `src/docxaicorrector/structure/layout_signals.py` (new).
- `tests/test_structure_layout_signals.py` (new).
- `pyrightconfig.json` (no change expected, but verify the new module is
  included by existing globs).

Acceptance:

- `derive_layout_signals([])` returns `LayoutSignals` with
  `body_baseline_pt is None`, empty tiers, empty records.
- `derive_layout_signals(paragraphs_with_mixed_fonts)` returns a record set
  that correctly identifies a 12 pt body baseline and an 18 pt heading tier
  on a synthetic mini-document.
- `derive_layout_signals` ignores paragraphs flagged
  `is_likely_page_number=True` and `is_repeated_across_pages=True`.
- `LayoutSignals.is_same_heading_tier(a, b)` returns `True` when two
  paragraphs share a heading tier and `False` when one of them has no font
  size.
- `LayoutSignals.is_page_break_between(a, b)` returns `True` only when both
  records carry concrete page hints and those hints differ; unknown/absent page
  hints must resolve conservatively to `False`.
- Round-trip test on a synthetic ten-paragraph fixture covers all branches
  of the bucketing logic, including the tie-break "prefer smallest tier" rule.

No production code path is changed by this commit. The flag is not yet wired.

### Commit 2: Wire Through `apply_document_map_topology`

Files:

- `src/docxaicorrector/structure/topology.py`.
- `src/docxaicorrector/processing/preparation.py`.
- `src/docxaicorrector/core/config_structure_sections.py`.
- `config.toml` (default `false`).
- `tests/test_structure_topology.py` (extend).
- `tests/test_config_structure_sections.py` (or equivalent existing config
  loader test; verify clamp and env override behavior).

Acceptance with `enabled = false`:

- `tests/test_structure_topology.py` continues to pass unchanged.
- Units and operations are semantically identical to today's disabled path. A
  targeted test asserts identical emitted projection content on a fixture map +
  paragraph set even though the cache key/schema version changes at rollout.

Acceptance with `enabled = true`:

- A synthetic fixture where the Stage 1 target already preserves the full
  chapter title or explicit `member_logical_indexes` from Phase 1b, and three
  continuation paragraphs share the heading font tier/style and remain short,
  produces a single `StructuralUnit` with four `logical_indexes` and
  `evidence` containing both `adjacent_short_heading_fragments` and
  `font_cluster_match`.
- The same fixture with one continuation paragraph at body-baseline font
  produces a unit with **two** `logical_indexes` (anchor + first matching
  continuation), not four. Font-cluster mismatch must reject continuation
  widening.
- A fixture where an observed page-hint transition exists between anchor and
  continuation is rejected from widening even if font tier matches.
- A fixture with a paragraph stem `"this page intentionally left blank chapter nine"`
  and a local authoritative heading target emits a
  `candidate_page_artifact_split` operation with `confidence == "candidate"`.
- The same fixture emits `page_break_boundary` only when the local window also
  carries a concrete page-hint transition.
- If the Stage 1 title is truncated and does not already cover the proposed
  members, no widened unit is emitted. Projection must fail closed rather than
  append the missing subtitle into `canonical_text`.
- The new `evidence` tags appear in `VALID_TOPOLOGY_EVIDENCE` and pass
  serialization validation.
- The new `candidate_page_artifact_split` op appears in
  `VALID_TOPOLOGY_OPERATIONS` and round-trips through the topology
  projection artifact JSON.

### Commit 3: Chapter Region Verification

Files:

- `tests/test_structure_topology_chapter_region.py` or extension of the
  existing chapter-region test module.
- If `lietaer-pdf-chapter-region-core` is not yet registered (Phase 0
  prerequisite from the parent spec), register it in `corpus_registry.toml`
  before this commit. If it is already registered, this commit only adds
  the assertions.

Acceptance on `lietaer-pdf-chapter-region-core` with `enabled = true`:

- Prerequisite: Phase 1b has already landed for this profile, and the Stage 1
  artifact for Chapter 11 preserves the full title and/or explicit member
  bounds needed by Variant A.
- Under that prerequisite, Chapter 11 heading produces a single
  `StructuralUnit` covering the multi-line title.
- `canonical_text` for that unit matches the Stage 1 canonical title and
  already includes `An Ancient Future?` (or the document's actual full title
  after extraction).
- No new `unmapped_target` fragments are introduced compared to baseline.
- Existing Chapter 9 recovery is preserved.
- The chapter-region structural diagnostic snapshot includes the
  `document_topology_layout_signals_built` event.

No full-book quality-gate rerun in this slice. Phase 4 parent-spec
acceptance covers structure-aware gate validation.

## Failure Modes And Honesty

This slice will **not** fix the following classes:

- Headings where Stage 1 emits no outline entry at all for the chapter. The
  layout widening requires an anchor target. If `DocumentMap.outline` and
  `toc_region.entries` both fail to anchor the chapter, no widening occurs.
- Headings where Stage 1 emits a truncated title or incomplete member boundary.
  This slice does not recover the missing suffix or member range from layout
  alone; Phase 1b remains the durable fix.
- Page-artifact splits in the absence of `DocumentMapSplitHint`. Only
  candidate diagnostics are produced. Binding remains Phase 3 work.
- Compound TOC splits. Out of scope for this slice (handled by Phase 3 with
  Stage 1 hints or one-to-one TOC entry matching).
- Bibliography, URL tails, list fragment regressions. Out of scope (per
  parent spec non-goals).
- Documents where LibreOffice loses `font_size_pt` entirely (rare but
  possible on heavily styled PDFs). The slice degrades gracefully: when
  fewer than 8 paragraphs have `font_size_pt`, the body baseline is `None`
  and widening returns to today's token-only behavior. No new failures.

These are documented up-front so that downstream agents do not over-extend
the slice.

## Risks

- Widening may accept false continuations when a short body paragraph in the
  same font tier sits adjacent to a real heading. Mitigated by:
  - the `_HEADING_CONTINUATION_WINDOW = 3` bound;
  - the `is_short_line` filter;
  - rejection on observed page-hint transitions when such hints exist;
  - same `style_cluster_id` requirement when present.
  In a counterfactual where the body baseline is incorrectly detected as
  matching the heading font (e.g., a monotone 12pt document with no
  font-based heading hierarchy), `derive_layout_signals` returns a
  `body_baseline_pt` equal to the only tier, `is_heading_tier=False` for all
  paragraphs, and widening cannot fire. Failure mode is "no improvement",
  not "false continuation".
- Cache-key bump invalidates existing `.run/document_topology/*` artifacts.
  This is expected and acceptable because the projection schema changes for the
  whole slice rollout.
- `candidate_page_artifact_split` diagnostics may grow in count. They are
  observability only; quality gates do not consume them. Retention policy
  is unchanged.
- `heading_ratio = 1.15` is a heuristic constant. It is configurable and
  clamped. A small follow-up may tune it per document profile if a real
  document needs a stricter or looser ratio.

## Verification Strategy

Canonical paths per repository contract.

Inner loop, in order:

```bash
bash scripts/test.sh tests/test_structure_layout_signals.py -q
bash scripts/test.sh tests/test_structure_topology.py -q
bash scripts/test.sh tests/test_structure_reconciliation.py -q
bash scripts/test.sh tests/test_structure_validation.py -q
bash scripts/test.sh tests/test_config_structure_sections.py -q
```

Structural diagnostic loop (after Commit 3):

```bash
bash scripts/run-structural-preparation-diagnostic.sh lietaer-pdf-chapter-region-core
```

Full-book diagnostic is **not** part of this slice's acceptance. It belongs
to the parent spec Phase 4 acceptance.

## Recommended Decision

Land in three commits in the order specified. Keep the feature flag default
`False` until Commit 3 passes the chapter-region diagnostic. Do not promote
the flag to `True` by default before:

- the parent spec Phase 2 acceptance criteria are demonstrably met on
  `lietaer-pdf-chapter-region-core`;
- the parent spec Phase 4 structure-aware gates are in place to absorb the
  changed `StructuralUnit` membership without surfacing it as a markdown
  regression on the full-book run;
- a documented runtime-cost measurement (single CPU pass, no I/O) confirms
  `derive_layout_signals` adds less than 50 ms on a 1000-paragraph book.

This is the smallest implementation-ready slice that adds layout-derived
evidence and candidate page-artifact diagnostics without violating Variant A.
It intentionally does **not** claim to close a truncated Stage 1 canonical-text
gap; that remains Phase 1b authority work.
