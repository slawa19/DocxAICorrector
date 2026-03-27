# Paragraph Boundary Normalization Spec

Date: 2026-03-27
Status: Proposed
Scope: New pre-processing stage for false DOCX paragraph break normalization, with an extensible normalization seam for related entity-boundary and attachment problems
Primary trigger: real-document cases where one logical body paragraph is split across multiple physical Word paragraphs and therefore propagates as broken Markdown / broken entity boundaries through the pipeline
Related specs:
- `docs/AI_STRUCTURE_RECOGNITION_SPEC_2026-03-26.md`
- `docs/ARCHITECTURE_REFACTORING_SPEC_2026-03-25.md`
- `docs/archive/specs/DOCUMENT_ENTITY_ROUNDTRIP_REFACTOR_SPEC_2026-03-21.md`

## 1. Problem Statement

The current pipeline treats every physical DOCX paragraph (`w:p`) as a canonical paragraph entity too early.

Today the boundary is established here:

1. `document.py` iterates document body blocks in source order.
2. Each DOCX paragraph is immediately converted into a `ParagraphUnit`.
3. A stable `paragraph_id` / `source_index` is assigned at this stage.
4. All downstream pipeline stages assume this entity boundary is correct.

This is a valid assumption only when the source DOCX uses paragraph boundaries semantically. Real documents often do not.

Observed failure class:

- one logical body paragraph is accidentally split across two or more physical Word paragraphs;
- the split often comes from PDF→DOCX / EPUB→DOCX conversion, OCR cleanup, manual layout edits, or style/template accidents rather than author intent;
- the preview then shows an empty line inside what should be one paragraph because the project renders one `ParagraphUnit` as one Markdown paragraph;
- marker mode correctly preserves the wrong boundary instead of fixing it;
- formatting restoration later receives the wrong source entity graph and can only preserve a broken interpretation.

This is not a UI-only problem and not an LLM-only problem. It is an architectural problem: the system promotes physical DOCX paragraph boundaries into canonical processing entities before verifying whether those boundaries are semantically real.

### 1.1. Concrete Symptom

Example shape seen in real documents:

```text
... архетипами: повторяющимися моделями
поведения во времени, наблюдаемыми в разных системах.
```

If these two lines arrive as two physical Word paragraphs, the current pipeline creates:

- `ParagraphUnit(text="... моделями", paragraph_id="p0123")`
- `ParagraphUnit(text="поведения во времени ...", paragraph_id="p0124")`

Then:

- `build_document_text()` joins them with `\n\n`;
- semantic blocks contain two paragraph entities instead of one;
- marker mode enforces two paragraph markers;
- the model is not allowed to merge them;
- the final DOCX and preview preserve the false split.

### 1.2. Why The Current Pipeline Cannot Repair This Durably

The current contracts intentionally preserve paragraph identity:

1. `ParagraphUnit.rendered_text` assumes one entity equals one Markdown paragraph or one heading/list item.
2. `build_marker_wrapped_block_text` emits one `[[DOCX_PARA_*]]` marker per `ParagraphUnit`.
3. Marker-mode prompt rules explicitly forbid merging paragraphs across markers.
4. `processed_paragraph_registry` expects a one-to-one relationship between paragraph markers and processed paragraph chunks.
5. `formatting_transfer.py` maps source and target paragraphs using paragraph-level identities and currently contains only limited one-source-to-many-target recovery (`accepted_split_targets`).

That means any attempt to patch this late in the pipeline fights the existing identity model instead of fixing the root cause.

## 2. Goals

1. Introduce a deterministic paragraph-boundary normalization stage before canonical paragraph identities are assigned.
2. Distinguish physical DOCX paragraphs from logical processing paragraphs as first-class concepts.
3. Merge only high-confidence false paragraph breaks and preserve all real semantic boundaries.
4. Keep the existing downstream pipeline largely intact by feeding it normalized logical paragraphs rather than raw physical paragraphs.
5. Preserve traceability from each logical paragraph back to the physical DOCX paragraphs it originated from.
6. Keep marker mode, semantic block construction, and formatting restoration coherent after normalization.
7. Make boundary-normalization decisions inspectable through diagnostics and testable through stable contracts.
8. Reserve one explicit normalization seam for closely related entity-boundary problems so the codebase does not accumulate separate one-off repairs for captions, TOC runs, epigraph pairs, and similar adjacency cases.

## 3. Non-Goals

This spec does not authorize the following:

- general-purpose text reflow or literary rewriting during extraction;
- broad AI-driven paragraph segmentation as the first implementation step;
- merging headings with body paragraphs;
- merging lists, captions, images, tables, or other explicitly structured entities;
- relaxing marker-mode paragraph preservation for already-normalized logical paragraphs;
- replacing Pandoc or rewriting the full rendering architecture;
- broad source-format round-trip fidelity work beyond what is needed for correct logical paragraph identity.
- Implementing every possible entity-grouping rule in Phase 1. This spec defines the seam and the roadmap, but the first implementation remains focused on false body-paragraph boundaries.

## 4. Protected Contracts

The following contracts remain protected throughout this change.

1. WSL-first runtime and test workflow remain unchanged.
2. Marker mode remains authoritative once logical paragraph identities have been established: the model must continue preserving one marker per logical paragraph.
3. Startup performance contract remains protected. Boundary normalization runs on the preparation path only.
4. Existing explicit structure semantics remain protected: headings, lists, captions, images, and tables must not be merged into body paragraphs by heuristic normalization.
5. Formatting restoration remains reference-DOCX-first and must not silently lose source traceability.

## 5. Current-State Root Cause Analysis

### 5.1. Boundary Promotion Happens Too Early

Current flow:

```text
DOCX physical blocks
  -> _iter_document_block_items(...)
  -> _build_paragraph_unit(...)
  -> ParagraphUnit assigned paragraph_id/source_index
  -> build_document_text / build_semantic_blocks / marker mode / formatting transfer
```

This flow collapses two different concepts into one model:

1. physical source paragraphs from DOCX;
2. logical editable paragraphs for the text pipeline.

Once `paragraph_id` is assigned, the rest of the system treats the boundary as canonical.

### 5.2. Downstream Systems Depend On That Canonical Boundary

The following downstream behaviors are boundary-sensitive:

1. Markdown preview and final source-text assembly.
2. Semantic block sizing and grouping.
3. Marker-mode generation contract.
4. Paragraph registry for post-generation mapping.
5. Output formatting diagnostics and source→target alignment.

Any local fix applied after paragraph identity assignment will create contract drift unless those downstream consumers are made boundary-aware.

### 5.3. Current Formatting Recovery Only Handles Split Targets, Not Merged Sources

`formatting_transfer.py` already tolerates one limited transformation shape:

- one source paragraph may become heading + body in the target, recorded as `accepted_split_targets`.

However, the inverse case is not modeled today:

- multiple physical source paragraphs are actually one logical source paragraph and should map to one target paragraph.

Without a first-class merged-source contract, the system can only preserve the broken source segmentation.

### 5.4. Similar Normalization Problems Exist For Other Entity Families

False body-paragraph breaks are not the only normalization problem in the repository.

There are adjacent classes of entity-boundary drift that share the same root cause: physical DOCX blocks are promoted too quickly into canonical processing entities without an explicit normalization/attachment pass.

Known or likely sibling cases:

1. **Heading prefix split**: one source text span is physically one paragraph or one logical unit, but downstream output becomes heading + body and must be treated as an accepted structural transform.
2. **Caption attachment drift**: a caption is physically just another paragraph, but semantically it belongs to the adjacent image or table and should be normalized as an attachment relation rather than a free body paragraph.
3. **Epigraph + attribution pairing**: quote text and author/source line are separate physical paragraphs, but semantically form one grouped construct.
4. **TOC header + TOC run grouping**: multiple short physical paragraphs are semantically part of one table-of-contents region and should be recognized as a grouped surface rather than unrelated body paragraphs.
5. **List continuation vs enumerated body text**: physical paragraph/list metadata may not align with the intended logical list entity.
6. **Review quote + attribution / dedication runs**: short adjacent paragraphs may form a single higher-level semantic construct even when they must remain separate final paragraphs.

These cases are not identical to false body-paragraph merges:

1. some require merging physical paragraphs into one logical paragraph;
2. some require preserving separate paragraphs but creating an explicit group or attachment relation;
3. some require reclassification rather than boundary merge.

The architecture should therefore introduce a general normalization seam, even though Phase 1 implements only one rule family.

## 6. Design Overview

### 6.1. High-Level Architecture

New target flow:

```text
DOCX file
    │
    ▼
┌────────────────────────────────────────────┐
│ Stage 0: Raw DOCX Extraction               │
│ Output: ordered list[RawBlock]             │
│   - RawParagraph                           │
│   - RawTable                               │
└────────────────────┬───────────────────────┘
                     │
                     ▼
┌────────────────────────────────────────────┐
│ Stage 1A: Boundary Repair                  │  ◄── NEW
│ Input: list[RawBlock]                      │
│ Output: repaired list[RawBlock]            │
│   - merges only false body-paragraph breaks│
└────────────────────┬───────────────────────┘
                     │
                     ▼
┌────────────────────────────────────────────┐
│ Stage 1B: Logical Entity Build             │  ◄── NEW
│ Input: repaired list[RawBlock]             │
│ Output: list[ParagraphUnit]                │
│   - canonical logical paragraphs           │
│   - canonical tables                       │
└────────────────────┬───────────────────────┘
                     │
                     ▼
┌────────────────────────────────────────────┐
│ Stage 2: Existing role classification      │
│ / AI structure recognition                 │
│ Input: canonical logical paragraphs        │
└────────────────────┬───────────────────────┘
                     │
                     ▼
┌────────────────────────────────────────────┐
│ Stage 3+: Existing pipeline                │
│ build_document_text                        │
│ build_semantic_blocks                      │
│ build_editing_jobs                         │
│ LLM generation with markers                │
│ formatting restoration                     │
└────────────────────────────────────────────┘
```

### 6.2. Core Architectural Rule

Canonical paragraph identity must be assigned after false-boundary repair, not before.

That means:

1. raw source paragraphs may keep raw indexes for diagnostics;
2. logical `paragraph_id` becomes the marker-level identity used by the pipeline;
3. each logical paragraph retains provenance information listing which raw paragraphs it absorbed.

### 6.3. Two Sub-Problems Inside Stage 1

This specification now explicitly defines Stage 1 as a normalization seam with two different responsibilities that must not be collapsed into one generic bucket.

Stage 1A is **boundary repair**:

1. `false_paragraph_boundary_merge`

Stage 1B is **logical entity build** from already-repaired raw blocks.

Later phases may add a narrowly scoped Stage 1C for relation normalization between already-built logical entities, for cases such as:

1. `caption_attachment_normalization`
2. `epigraph_attribution_grouping`
3. `toc_region_grouping`
4. `list_continuation_normalization`

The decision rule for the codebase is:

1. if a problem is about repairing a false physical paragraph boundary, it belongs in Stage 1A;
2. if a problem is about building canonical logical entities from repaired raw blocks, it belongs in Stage 1B;
3. if a problem is about semantic relations between already-correct logical entities, it belongs in a later relation-normalization stage, not in boundary repair;
4. if a problem is about semantic role classification of already-correct logical entities, it belongs in structure recognition;
5. if a problem is purely about final rendering policy, it belongs downstream in rendering/formatting.

This separation prevents repeated one-off fixes in preview, semantic block builder, formatting transfer, or an overgrown catch-all normalization module.

## 7. New Data Model

### 7.1. Raw Extraction Layer

Add a raw extraction model that represents physical DOCX blocks without prematurely turning them into canonical processing paragraphs.

```python
@dataclass(frozen=True)
class RawParagraph:
    raw_index: int
    text: str
    style_name: str
    paragraph_alignment: str | None
    is_bold: bool
    font_size_pt: float | None
    explicit_heading_level: int | None
    list_kind: str | None
    list_level: int
    list_numbering_format: str | None
    list_num_id: str | None
    list_abstract_num_id: str | None
    role_hint: str
    source_xml_fingerprint: str | None = None


@dataclass(frozen=True)
class RawTable:
    raw_index: int
    html_text: str
    asset_id: str


RawBlock = RawParagraph | RawTable
```

Notes:

1. `role_hint` is allowed at raw level but is not yet canonical.
2. `raw_index` is the physical order in the DOCX body.
3. `RawParagraph` intentionally stores the metadata needed for merge decisions without exposing the whole `python-docx Paragraph` object downstream.

### 7.2. Phase 1 Canonical Logical Entity

Phase 1 makes one explicit design choice:

**`ParagraphUnit` remains the canonical logical paragraph entity for the mainline pipeline.**

The new work does not introduce a second long-lived paragraph model that competes with `ParagraphUnit` at runtime.

Instead:

1. Stage 0 produces raw extraction models used only inside extraction/repair;
2. Stage 1A repairs false physical paragraph boundaries;
3. Stage 1B builds canonical `ParagraphUnit` instances from the repaired raw blocks;
4. all downstream pipeline stages continue consuming `ParagraphUnit`.

`LogicalParagraph` below is therefore illustrative of the logical shape that `ParagraphUnit` must represent after Stage 1B, not a second canonical runtime type.

```python
@dataclass
class LogicalParagraph:
    text: str
    role: str
    paragraph_alignment: str | None
    heading_level: int | None
    heading_source: str | None
    list_kind: str | None
    list_level: int
    list_numbering_format: str | None
    list_num_id: str | None
    list_abstract_num_id: str | None
    paragraph_id: str
    source_index: int
    structural_role: str
    role_confidence: str

    # New provenance fields
    origin_raw_indexes: list[int]
    origin_raw_texts: list[str]
    boundary_source: str          # "raw" | "normalized_merge"
    boundary_confidence: str      # "explicit" | "high" | "medium"
    boundary_rationale: str | None = None
```

Notes:

1. In Phase 1 these fields should be added to `ParagraphUnit` rather than introducing a competing long-lived `LogicalParagraph` runtime model.
2. Any future standalone logical-entity type would require a separate approved refactoring spec; it is not part of this change.

### 7.3. Future Relation Metadata

To support future non-merge normalization families without another datamodel rewrite, relation metadata should be modeled explicitly as relations produced by a later relation-normalization stage, rather than as paragraph-only ownership fields.

Suggested future shape:

```python
@dataclass(frozen=True)
class LogicalRelation:
    relation_id: str
    relation_kind: str          # "image_caption" | "epigraph_pair" | "toc_region"
    source_logical_ids: tuple[str, ...]
    target_logical_id: str | None = None
    confidence: str = "high"
```

Phase 1 does not implement relation normalization. The important design choice is to reserve a first-class relation model for later phases so grouping/attachment concerns do not get tunneled through paragraph-centric fields.

### 7.4. Normalization Diagnostics

```python
@dataclass(frozen=True)
class ParagraphBoundaryDecision:
    left_raw_index: int
    right_raw_index: int
    decision: str                 # "merge" | "keep"
    confidence: str               # "high" | "medium" | "blocked"
    reasons: tuple[str, ...]


@dataclass
class ParagraphBoundaryNormalizationReport:
    total_raw_paragraphs: int
    total_logical_paragraphs: int
    merged_group_count: int
    merged_raw_paragraph_count: int
    decisions: list[ParagraphBoundaryDecision]
```

This report should be saved in debug artifacts similarly to other processing diagnostics.

### 7.5. Future Relation-Level Diagnostics

When later relation-normalization families are implemented, the same reporting surface should expand to include non-merge decisions such as:

1. attachment established (`caption` -> `image` / `table`),
2. grouped region established (`toc_header` + `toc_entry` sequence),
3. grouped pair established (`epigraph` + `attribution`).

This should remain one diagnostics family rather than several unrelated artifact formats.

## 8. Normalization Rules

### 8.1. Phase 1 Taxonomy

The broader normalization architecture supports three distinct operation types:

1. **Merge**: multiple raw paragraphs become one logical paragraph.
2. **Group**: multiple raw/logical paragraphs remain separate but gain an explicit group relation.
3. **Attach**: a logical paragraph remains separate but is attached semantically to a neighboring non-paragraph entity such as an image or table.

Phase 1 implements only **Merge** for false body-paragraph breaks.

Future phases may add **Group** and **Attach** operations, but those belong in a later relation-normalization stage after canonical logical entities already exist.

### 8.2. Decision Principle

Boundary normalization must be conservative.

The system is not trying to improve prose or infer high-level semantics. It is trying to normalize mismatches between physical DOCX blocks and the canonical entities needed by the pipeline.

For Phase 1, that means deciding whether a physical paragraph boundary is false and should be removed before the text pipeline begins.

### 8.3. Hard No-Merge Rules

Never merge across a boundary when any of the following is true:

1. either side is an image, table, or explicit caption;
2. either side has explicit heading style / outline level;
3. either side is an explicit list item or carries list numbering metadata;
4. the right paragraph begins with an explicit list marker;
5. the right paragraph is recognized as a likely caption, attribution line, TOC entry, or dedication line;
6. the left paragraph ends with strong paragraph-final punctuation and the right paragraph begins with a clear new-sentence/title signal;
7. paragraph alignment changes across the boundary in a way that implies structure, not continuation;
8. style transition strongly implies structure change (`Body Text` -> `Heading 2`, `Normal` -> `Caption`, etc.);
9. a table or image block exists between the candidate paragraphs.

These blocked merge boundaries may still become valid **group** or **attachment** candidates in later phases. For example:

1. a caption near an image should not merge, but may attach;
2. an attribution after an epigraph should not merge, but may group;
3. TOC entry sequences should not merge into one paragraph, but may form a grouped region.

### 8.4. Positive Merge Signals

Prefer merge when a substantial majority of the following are true:

1. both sides are body-like paragraphs by raw role hint;
2. style names are identical or highly compatible;
3. alignment is identical or both are effectively left/default body alignment;
4. list metadata is absent on both sides;
5. the left paragraph does not end with terminal punctuation (`.`, `!`, `?`, `…`) and is not clearly syntactically complete;
6. the right paragraph starts with a lowercase word, digit, connective, or mid-sentence continuation shape;
7. the combined string reads as a grammatically plausible sentence/paragraph without needing punctuation insertion beyond a single space;
8. the right paragraph is short and continuation-like, or the left paragraph is suspiciously short and unfinished;
9. font/style metadata remains consistent across both raw paragraphs.

### 8.5. Merge Confidence Tiers

Suggested confidence bands:

1. `high`: deterministic continuation shape, no structural conflicts, strong continuation signals.
2. `medium`: likely continuation but at least one weaker signal or mild ambiguity.
3. `blocked`: merge was considered but prevented by a no-merge rule.

Phase 1 applies only `high` merges by default.

`medium` can be logged for diagnostics and optionally enabled later behind config.

### 8.6. Merge Output Text Policy

When two raw paragraphs are merged:

1. text is joined with a single space by default;
2. double spaces and accidental space-before-punctuation artifacts are normalized conservatively;
3. no punctuation is invented except whitespace cleanup;
4. inline markup and placeholders remain in source order;
5. the merged logical paragraph inherits body-level metadata from the dominant raw paragraph, usually the first paragraph in the group.

### 8.7. Future Relation-Normalization Rule Families

The following rule families are intentionally reserved for later phases after Phase 1 boundary repair is stable.

#### 8.7.1. Caption attachment normalization

Goal:

1. establish a stable semantic relation between caption paragraph and adjacent image/table;
2. preserve separate paragraph identity while preventing the caption from drifting into ordinary body flow.

Likely signals:

1. lexical caption markers;
2. immediate adjacency to image/table block;
3. short caption-like length;
4. explicit caption style when available.

Operation type: **Attach**, not Merge. Implementation belongs in a later relation-normalization stage, not in Phase 1 boundary repair.

#### 8.7.2. Epigraph-attribution grouping

Goal:

1. preserve quote and attribution as separate paragraphs;
2. keep them as one grouped construct for chunking, rendering, and formatting decisions.

Likely signals:

1. short centered quote paragraph followed by source/author line;
2. attribution markers such as dash prefix, all-caps author line, or author/source keywords;
3. local proximity to heading or chapter start.

Operation type: **Group**, not Merge. Implementation belongs in a later relation-normalization stage, not in Phase 1 boundary repair.

#### 8.7.3. TOC region grouping

Goal:

1. treat `toc_header` plus contiguous `toc_entry` lines as one structured region;
2. avoid treating them as ordinary body paragraphs during editing/block formation.

Operation type: **Group**, not Merge. Implementation belongs in a later relation-normalization stage, not in Phase 1 boundary repair.

#### 8.7.4. List continuation normalization

Goal:

1. distinguish genuine list entities from enumerated body content and accidental DOCX list metadata;
2. preserve list region boundaries more deliberately.

This family may involve both **Group** and reclassification behavior, but it should be specified separately from Phase 1 boundary repair and not silently accumulate inside the initial merge implementation.

## 9. Integration Into Existing Pipeline

### 9.1. New Insertion Point

The correct insertion point is inside `extract_document_content_from_docx` or an immediately adjacent helper layer, before final paragraph identity assignment.

New conceptual flow:

```python
def extract_document_content_from_docx(uploaded_file):
    raw_blocks = extract_raw_document_blocks(uploaded_file)
    normalized_blocks, boundary_report = normalize_false_paragraph_breaks(raw_blocks)
    paragraphs, image_assets = build_logical_paragraph_units(normalized_blocks)
    _reclassify_adjacent_captions(paragraphs)
    _promote_short_standalone_headings(paragraphs, ...)
    return paragraphs, image_assets, boundary_report
```

Implementation detail:

1. `image_assets` collection can still happen during raw extraction.
2. Caption reclassification and short-heading promotion should operate on normalized logical paragraphs, not raw physical paragraphs.

### 9.2. Relationship To AI Structure Recognition

Boundary normalization must happen before AI structure recognition.

Correct order:

1. extract raw physical paragraphs;
2. normalize false paragraph boundaries into logical paragraphs;
3. assign logical paragraph identities;
4. run heuristic / AI structure recognition on logical paragraphs.

Reason:

- structure recognition should classify semantically valid paragraph units, not artifacts of broken segmentation.

### 9.3. Cache Key Impact

The preparation cache key must include the paragraph-boundary normalization mode because it changes the normalized paragraph set and therefore downstream outputs.

Minimum extension:

```python
build_prepared_source_key(
    uploaded_file_token,
    chunk_size,
    *,
    structure_recognition_enabled=False,
    paragraph_boundary_normalization_enabled=True,
)
```

If future phases add normalization policy levels (`off`, `high_only`, `high_and_medium`), the key must include the effective mode rather than a single bool.

## 10. Impact On Marker Mode

Marker mode stays in place, but its identity anchor shifts from physical paragraphs to logical paragraphs.

This is the intended result.

Before:

- one physical DOCX paragraph = one marker.

After normalization:

- one logical editable paragraph = one marker;
- a marker may correspond to multiple raw source paragraphs through provenance metadata;
- the model still must not merge or split logical paragraphs across markers.

This keeps the LLM contract stable while fixing the input entity graph.

Future note:

1. grouped or attached entities may still keep separate markers if they remain separate logical paragraphs;
2. marker mode should reflect logical paragraph identity, not higher-level group identity.

## 11. Impact On Formatting Restoration

### 11.1. New Mapping Shape

Formatting restoration must gain first-class support for merged-source groups.

New accepted mapping shape:

- many raw source paragraphs -> one logical source paragraph -> one target paragraph

This is distinct from the existing accepted split-target shape:

- one logical source paragraph -> heading target + body target

### 11.2. Dominant Source Paragraph Rule

For a logical paragraph built from multiple raw source paragraphs, formatting restoration should use a dominant raw paragraph as the style baseline.

Default rule:

1. choose the first raw paragraph in the merged group as the dominant source;
2. preserve the full list of absorbed raw indexes for diagnostics;
3. treat the remaining raw paragraphs as consumed by the logical source entity, not as unmapped leftovers.

Rationale:

1. false paragraph splits typically share the same body styling;
2. using the first raw paragraph preserves the least surprising style baseline;
3. diagnostics remain honest about what happened.

### 11.3. New Diagnostics Surface

Add `accepted_merged_sources` diagnostics parallel to `accepted_split_targets`.

Suggested shape:

```json
{
  "logical_paragraph_id": "p0123",
  "origin_raw_indexes": [123, 124],
  "dominant_raw_index": 123,
  "kind": "false_paragraph_boundary_merge",
  "target_index": 118,
  "target_text_preview": "...",
  "source_text_preview": "..."
}
```

This prevents merged-source normalization from appearing as mysterious dropped paragraphs in diagnostics.

## 12. Configuration

New config section:

```toml
[paragraph_boundary_normalization]
enabled = true
mode = "high_only"                 # "off" | "high_only" | "high_and_medium"
save_debug_artifacts = true
```

Phase 1 rollout recommendation:

1. default enabled in production config only after targeted validation;
2. initial development default may be enabled with `high_only` because merges are conservative;
3. `high_and_medium` remains future/experimental.

Future relation-normalization families must not introduce public config keys until at least one implemented behavior exists.

## 13. Diagnostics And Artifacts

Save normalization diagnostics under:

- `.run/paragraph_boundary_reports/<filename>_<hash8>.json`

Artifact shape:

```json
{
  "version": 1,
  "source_file": "example.docx",
  "source_hash": "a1b2c3d4",
  "mode": "high_only",
  "total_raw_paragraphs": 1806,
  "total_logical_paragraphs": 1784,
  "merged_group_count": 22,
  "merged_raw_paragraph_count": 44,
  "decisions": [
    {
      "left_raw_index": 157,
      "right_raw_index": 158,
      "decision": "merge",
      "confidence": "high",
      "reasons": [
        "same_body_style",
        "left_not_terminal",
        "right_starts_lowercase",
        "no_structural_conflict"
      ]
    }
  ]
}
```

## 14. Verification Criteria

### Must-pass before merge

1. False body-paragraph break with identical style and continuation syntax is merged into one logical paragraph.
2. Real paragraph boundary between two body paragraphs is preserved when terminal punctuation and new-sentence signals indicate separation.
3. Heading-to-body boundary is never merged.
4. List items are never merged into surrounding body paragraphs.
5. Captions remain separate paragraphs and preserve adjacency behavior.
6. Marker mode still emits exactly one marker per logical paragraph.
7. Processed paragraph registry still matches marker counts after normalization.
8. Formatting diagnostics do not report consumed raw paragraphs as unexplained unmapped source leftovers.
9. Existing tests for semantic block construction continue to pass.
10. Existing tests for marker-mode validation continue to pass.
11. Existing tests for accepted split-target formatting recovery continue to pass.
12. Preparation cache key tests are updated for normalization mode.

### Real-document validation criteria

13. The known climate/example paragraph no longer appears as two Markdown paragraphs in preview or final Markdown.
14. The Lietaer real document no longer shows spurious empty lines for known continuation cases.
15. No regression in heading counts, list preservation, or caption handling on the protected real-document validation profile.

## 15. Test Plan

### 15.1. New unit tests

Add `tests/test_paragraph_boundary_normalization.py` with coverage for:

1. deterministic merge of two body raw paragraphs;
2. no merge after terminal punctuation + sentence reset;
3. no merge when right paragraph looks like heading;
4. no merge for explicit list metadata;
5. no merge around captions/images/tables;
6. provenance fields populated correctly after merge;
7. merged logical paragraph text spacing normalized correctly.

### 15.2. Existing test updates

Update or extend:

1. `tests/test_document.py` for extraction / marker-wrapped text expectations with logical paragraphs.
2. `tests/test_preparation.py` for cache-key changes.
3. `tests/test_format_restoration.py` for `accepted_merged_sources` diagnostics.
4. `tests/test_document_pipeline.py` for marker registry integrity after normalization.

### 15.3. Integration tests

Add one synthetic DOCX fixture with an intentional false paragraph split and verify:

1. extraction returns one logical paragraph;
2. built Markdown contains no blank line between the two fragments;
3. marker mode uses one marker;
4. output DOCX produces one restored paragraph.

Add real-document targeted validation selector for known merged-boundary cases.

## 16. Rollout Plan

### Phase 1: Deterministic boundary normalization

1. Introduce raw extraction model.
2. Add conservative high-confidence boundary-normalization stage.
3. Propagate provenance metadata into logical paragraph units.
4. Add diagnostics artifacts.
5. Update formatting diagnostics to understand merged-source groups.

### Phase 2: Relation-normalization spec and implementation

1. Write a separate approved spec for relation normalization over already-built logical entities.
2. Add non-merge normalization operations for caption attachment, epigraph-attribution grouping, and TOC region grouping.
3. Propagate relation metadata into semantic block formation and diagnostics.
4. Keep marker identity paragraph-level while honoring relations in chunking/rendering decisions.

### Phase 3: Configurable medium-confidence merge mode

1. Add optional `high_and_medium` behavior behind config.
2. Expand diagnostics review tooling if needed.
3. Validate against multiple real-document profiles.

### Phase 4: Optional AI-assisted normalization review

Only if deterministic normalization leaves too many unresolved cases:

1. feed ambiguous candidate boundaries to a small AI classifier;
2. optionally feed ambiguous grouping candidates to a small AI classifier;
3. never let AI override explicit structural boundaries;
4. keep deterministic `high` rules as the default path.

This phase is explicitly optional and not required for the main architecture fix.

## 17. Implementation Plan

This section is the implementation-ready execution plan for the Phase 1 scope only.

### 17.1. Scope Guard

Phase 1 implementation must stay inside these boundaries:

1. only false body-paragraph boundary repair;
2. no relation normalization for captions, epigraph pairs, TOC regions, or list-group families;
3. no AI-assisted boundary decisions;
4. no UI-only workaround as a substitute for entity repair;
5. no second canonical paragraph model beyond `ParagraphUnit` in runtime.

If a change request goes beyond these constraints, it requires either:

1. a follow-up Phase 2 task under this spec; or
2. a new approved spec for relation normalization.

### 17.2. PR Slice 1 - Raw Extraction Boundary

- Files: `document.py`, `models.py`, targeted tests
- Tasks:
  - introduce raw extraction data structures for physical DOCX blocks;
  - split current extraction into raw extraction vs canonical `ParagraphUnit` construction;
  - keep behavior unchanged when boundary repair is disabled or yields no merges.
- Acceptance:
  - extraction still preserves document order;
  - no downstream caller needs to consume raw models directly;
  - existing extraction tests still pass or are updated only for the new internal contract.

### 17.3. PR Slice 2 - Boundary Repair Engine

- Files: `document.py`, `models.py`, new tests
- Tasks:
  - implement Stage 1A false-boundary repair for high-confidence body-paragraph merges only;
  - carry provenance from absorbed raw paragraphs;
  - normalize merged text spacing conservatively.
- Acceptance:
  - known false-split case becomes one logical paragraph;
  - hard no-merge rules protect headings, lists, captions, tables, and images;
  - merged logical paragraphs are built as canonical `ParagraphUnit` instances.

### 17.4. PR Slice 3 - Preparation And Cache Contract

- Files: `preparation.py`, `config.py`, `config.toml`, tests
- Tasks:
  - add config wiring for Phase 1 normalization mode;
  - include normalization mode in preparation cache key;
  - optionally emit preparation diagnostics/progress counters if useful.
- Acceptance:
  - cache invalidates correctly when normalization mode changes;
  - disabled mode reproduces legacy behavior;
  - config tests cover defaults and overrides.

### 17.5. PR Slice 4 - Marker And Pipeline Integrity

- Files: `document.py`, `document_pipeline.py`, related tests
- Tasks:
  - ensure marker generation uses repaired logical paragraphs only;
  - verify processed paragraph registry still aligns one-to-one with logical paragraph IDs;
  - keep semantic block builder behavior stable apart from corrected paragraph boundaries.
- Acceptance:
  - marker mode still rejects paragraph splits inside one logical marker;
  - processed paragraph registry counts remain stable;
  - preview/final Markdown no longer shows false split for protected fixtures.

### 17.6. PR Slice 5 - Formatting Diagnostics And Mapping

- Files: `formatting_transfer.py`, `tests/test_format_restoration.py`, possibly `models.py`
- Tasks:
  - add merged-source awareness to formatting diagnostics;
  - introduce `accepted_merged_sources` or equivalent diagnostics surface;
  - ensure consumed raw paragraphs are not misreported as unexplained mapping failures.
- Acceptance:
  - merged-source normalization appears explicitly in diagnostics;
  - existing split-target behavior still passes;
  - no regression in output formatting diagnostics for protected fixtures.

### 17.7. PR Slice 6 - Real-Document Validation

- Files: validation profiles/tests/artifacts as needed
- Tasks:
  - add targeted validation coverage for known false-split paragraphs;
  - confirm no regression in heading/list/caption behavior on protected real documents.
- Acceptance:
  - known real-document false-split samples are repaired;
  - protected real-document validation remains green or within approved thresholds.

## 18. Implementation Checklist

Use this checklist as the execution tracker during implementation.

Review note (2026-03-27): this checklist was adjusted based on code inspection of the current implementation. No full WSL test run was performed as part of this review.

Implementation follow-up (2026-03-27): a subsequent user-visible verification pass was completed with `Run Full Pytest` (`664 passed, 6 skipped`) and `Run Lietaer Real Validation` (`run_id=20260327T095709Z_10396_1`, `status=completed`, `acceptance_passed=True`). The real-document harness now includes explicit known false-split acceptance checks for the canonical Lietaer continuation case.

### 18.1. Spec And Scope Discipline

- [x] Implementation is explicitly limited to Phase 1 body-paragraph boundary repair.
- [x] No relation-normalization behavior is added under the same change set.
- [x] No second canonical runtime paragraph model is introduced.

### 18.2. Raw Extraction And Entity Build

- [x] Raw extraction model for physical DOCX blocks is introduced.
- [x] Current extraction path is split into raw extraction and canonical `ParagraphUnit` construction.
- [x] Canonical `ParagraphUnit` identities are assigned only after boundary repair.
- [x] `ParagraphUnit` carries provenance fields for absorbed raw paragraphs.

### 18.3. Boundary Repair Logic

- [x] High-confidence false body-paragraph merge logic is implemented.
- [x] Hard no-merge rules cover headings, lists, captions, images, and tables.
- [x] Merged text spacing is normalized conservatively.
- [x] Repair decisions are captured in a normalization report artifact.

### 18.4. Preparation And Config

- [x] Phase 1 config wiring is added to `config.py` and `config.toml`.
- [x] Preparation cache key includes normalization mode.
- [x] Disabled normalization mode reproduces legacy behavior.

### 18.5. Pipeline Integrity

- [x] Marker generation uses repaired logical paragraphs.
- [x] Processed paragraph registry still matches logical paragraph IDs.
- [x] Semantic block building remains stable apart from corrected boundaries.
- [x] Preview and final Markdown no longer show protected false-split cases.

### 18.6. Formatting And Diagnostics

- [x] Formatting diagnostics understand merged-source groups.
- [x] `accepted_merged_sources` or equivalent diagnostics surface is added.
- [x] Consumed raw paragraphs are not reported as unexplained unmapped leftovers.

### 18.7. Tests

- [x] New focused unit tests are added for false-boundary repair.
- [x] Existing extraction tests are updated where needed.
- [x] Cache-key tests are updated.
- [x] Marker-mode tests still pass.
- [x] Formatting restoration tests still pass.
- [x] Real-document targeted validation covers known false-split cases.

### 18.8. Done Criteria

- [x] All Phase 1 must-pass verification criteria in this spec are satisfied.
- [x] No Phase 2 relation-normalization scope leaked into the implementation.
- [x] The implementation remains consistent with the canonical decision rule in this spec.

## 19. File Inventory

| File | Action | Description |
|------|--------|-------------|
| `document.py` | Modify | Split raw extraction from logical paragraph construction; insert normalization stage |
| `models.py` | Modify | Add raw block / provenance / normalization-report data structures or extend `ParagraphUnit` |
| `preparation.py` | Modify | Include normalization mode in cache key and optional progress reporting |
| `formatting_transfer.py` | Modify | Accept merged-source diagnostics / mapping behavior |
| `config.py` / `config.toml` | Modify | Add paragraph boundary normalization config |
| `tests/test_paragraph_boundary_normalization.py` | Create | New focused tests |
| `tests/test_document.py` | Modify | Adjust extraction and marker expectations |
| `tests/test_preparation.py` | Modify | Cache-key coverage |
| `tests/test_format_restoration.py` | Modify | `accepted_merged_sources` coverage |
| `tests/test_document_pipeline.py` | Modify | Marker-registry integrity with normalized paragraphs |

## 20. Open Questions — Resolved

### 18.1. Should this be solved in UI / preview only?

No.

That would hide the symptom while leaving the wrong entity graph intact for:

1. generation prompts,
2. markers,
3. formatting restoration,
4. diagnostics,
5. final DOCX.

### 18.2. Should the model be allowed to merge paragraphs instead?

No.

The current marker-mode contract correctly protects paragraph identity once the identity is correct. The fix is to establish the right logical identity before marker assignment, not to weaken marker preservation.

### 18.3. Should normalization happen before or after structure recognition?

Before.

Structure recognition should classify normalized logical paragraphs, not artifacts caused by broken physical DOCX boundaries.

### 18.4. Is a full IR refactor required first?

No.

This change can be implemented as a focused pre-processing contract hardening step inside the current architecture. It aligns with the longer-term document-IR direction, but does not require a full entity-graph rewrite before delivering value.

### 18.5. Should the spec explicitly anticipate similar problems for other entities?

Yes.

However, the correct shape is not to broaden Phase 1 into a repo-wide structural rewrite.

The spec now explicitly reserves a broader normalization architecture for three operation types:

1. merge,
2. group,
3. attach.

Phase 1 still implements only false body-paragraph boundary merges. Later phases may add caption attachment, epigraph-attribution grouping, TOC-region grouping, and list-continuation normalization, but only through a separately specified relation-normalization stage rather than by expanding Phase 1 into a catch-all module.

## 21. Implementation Decision Rule

Default decision rule for implementation:

1. fix false paragraph boundaries at the earliest boundary-aware stage;
2. preserve traceability to absorbed raw paragraphs;
3. keep marker mode strict after normalization;
4. teach formatting diagnostics to understand merged-source groups;
5. do not patch preview/UI in place as a substitute for entity-contract repair.
