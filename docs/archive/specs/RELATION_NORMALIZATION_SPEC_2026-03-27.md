# Relation Normalization Spec

Date: 2026-03-27
Status: Informational extract only; superseded as an authoritative implementation contract by docs/archive/specs/PARAGRAPH_BOUNDARY_NORMALIZATION_SPEC_2026-03-27.md
Scope: Phase 2 relation normalization over already-built logical paragraphs and adjacent assets, without introducing a second canonical paragraph model
Primary trigger: Phase 1 fixed false body-paragraph merges, but the pipeline still lacks a first-class way to represent non-merge semantic adjacency such as caption attachment, epigraph-attribution pairs, and TOC regions
Related specs:
- `docs/archive/specs/PARAGRAPH_BOUNDARY_NORMALIZATION_SPEC_2026-03-27.md`
- `docs/archive/specs/AI_STRUCTURE_RECOGNITION_SPEC_2026-03-26.md`
- `docs/archive/specs/ARCHITECTURE_REFACTORING_SPEC_2026-03-25.md`

This document remains useful as a focused extract for Phase 2 discussion, but it is no longer the repository's authoritative source of truth for normalization implementation order, contracts, or acceptance criteria.

## 1. Problem Statement

Phase 1 solved one specific boundary error: a single logical body paragraph being split into multiple physical DOCX paragraphs.

That was the right first step, but it deliberately did not solve non-merge relation problems. The current pipeline still has no durable relation layer for cases where two or more already-valid logical paragraphs should remain distinct entities while still being treated as one semantic cluster for chunking, rendering, diagnostics, or formatting analysis.

Current unresolved classes:

1. caption attachment: an image or table caption is a separate paragraph, but semantically belongs to the adjacent asset and should travel with it through semantic block formation and diagnostics;
2. epigraph-attribution pairing: the quote paragraph and the source/author paragraph are distinct logical paragraphs, but semantically form one grouped construct;
3. TOC region grouping: a TOC header followed by TOC entries should be treated as one region rather than independent free body/list paragraphs during chunking and diagnostics.

Today these cases are handled only partially and inconsistently:

1. `ParagraphUnit.attached_to_asset_id` already captures direct caption adjacency, but there is no first-class relation artifact and no generalized relation policy;
2. `build_semantic_blocks()` has a narrow hard-coded image/table plus caption rule, but no equivalent mechanism for epigraph-attribution pairs or TOC regions;
3. `structural_role` from AI structure recognition can label `epigraph`, `attribution`, `toc_header`, and `toc_entry`, but current consumers do not convert those labels into stable grouping behavior;
4. diagnostics serialize paragraph metadata, but do not report normalized relation decisions as a dedicated contract.

This creates a structural gap: the codebase has paragraph normalization and paragraph metadata, but not a stable representation of paragraph-to-paragraph and paragraph-to-asset relations.

## 2. Goals

1. Add one deterministic relation-normalization stage for non-merge semantic adjacency after logical paragraphs exist.
2. Keep `ParagraphUnit` as the canonical paragraph entity and avoid introducing a competing runtime paragraph model.
3. Represent relations explicitly so chunking, rendering, diagnostics, and validation can consume the same contract.
4. Generalize beyond captions to cover at least epigraph-attribution grouping and TOC region grouping.
5. Preserve paragraph identity, marker identity, and source traceability from Phase 1.
6. Make relation decisions inspectable through diagnostics artifacts and testable via stable contracts.

## 3. Non-Goals

This spec does not authorize the following:

1. merging distinct logical paragraphs into one text paragraph;
2. changing the WSL-first runtime contract, startup contract, or test workflow contract;
3. introducing AI-driven relation decisions in Phase 2;
4. redesigning the entire document IR, semantic block model, or formatting-transfer architecture;
5. suppressing TOC content from editing altogether as part of relation normalization alone;
6. retrofitting UI-only fixes instead of a pipeline-level relation contract.

## 4. Protected Contracts

The following contracts remain protected throughout Phase 2:

1. `ParagraphUnit` remains the canonical paragraph entity consumed by the runtime pipeline.
2. Paragraph markers remain paragraph-level; relation normalization may group paragraphs for block formation, but must not collapse multiple paragraph identities into one marker.
3. Phase 1 paragraph-boundary normalization remains the earlier stage for false body-paragraph merges and must not be broadened into a catch-all relation module.
4. The pipeline must remain production-compatible for real-document validation and formatting restoration.
5. The solution must preserve or improve current startup behavior and must not add heavy synchronous startup work.

## 5. Current-State Baseline

The repository already contains several partial ingredients that Phase 2 should formalize rather than replace.

### 5.1. Existing useful fields

1. `ParagraphUnit.attached_to_asset_id` already records direct caption-to-asset linkage for adjacent captions.
2. `ParagraphUnit.structural_role` and `role_confidence` already carry richer semantic signals such as `epigraph`, `attribution`, `toc_header`, and `toc_entry`.
3. Formatting diagnostics already serialize these fields, so additional relation metadata can extend an existing diagnostic path rather than invent a new side channel.

### 5.2. Existing gaps

1. `build_semantic_blocks()` contains hard-coded caption handling but no reusable relation abstraction.
2. There is no dedicated relation-normalization report analogous to the Phase 1 boundary report.
3. Real-document structural validation measures merged-source diagnostics, but not relation-normalization outcomes.
4. TOC and epigraph grouping behavior is still implicit, inconsistent, or absent.

## 6. Proposed Architecture

### 6.1. Pipeline placement

Add a new deterministic Stage 1C relation-normalization step after logical paragraphs are built and after any structure-recognition enrichment has been applied, but before semantic block construction.

Target sequence:

1. raw DOCX extraction;
2. Phase 1 false paragraph-boundary normalization;
3. canonical `ParagraphUnit` construction;
4. optional structure-recognition enrichment;
5. Phase 2 relation normalization;
6. relation-aware semantic block construction and downstream processing.

This ordering matters:

1. relation normalization should reason over already-correct logical paragraphs, not raw physical fragments;
2. if AI structure recognition is enabled, relation normalization should consume the improved `structural_role` labels rather than weaker heuristics.

### 6.2. Relation model

Introduce one explicit relation artifact rather than tunneling all behavior through paragraph-local flags.

Proposed dataclasses:

```python
@dataclass(frozen=True)
class ParagraphRelation:
    relation_id: str
    relation_kind: str
    member_paragraph_ids: tuple[str, ...]
    anchor_asset_id: str | None = None
    confidence: str = "high"
    rationale: tuple[str, ...] = ()


@dataclass(frozen=True)
class RelationNormalizationReport:
    total_relations: int
    relation_counts: dict[str, int]
    rejected_candidate_count: int
    decisions: list[RelationDecision]
```

Important constraint: this relation list complements `ParagraphUnit`; it does not replace it.

### 6.3. Relation kinds in Phase 2

Phase 2 should implement only these deterministic relation kinds:

1. `image_caption` and `table_caption`
2. `epigraph_attribution`
3. `toc_region`

Other possible relation kinds such as list-family grouping or footnote-reference grouping are explicitly deferred until a later spec.

## 7. Relation Detection Rules

### 7.1. Caption attachment

Detection should normalize the existing caption behavior into a first-class relation decision.

Rules:

1. if a caption paragraph is adjacent to an image or table asset and the existing caption heuristics accept the pairing, create a relation anchored to that asset;
2. preserve `attached_to_asset_id` for compatibility, but derive it from the relation decision rather than treating it as the only contract;
3. do not attach across intervening body paragraphs or across multiple candidate assets without a deterministic winner;
4. if the candidate is ambiguous, keep the paragraph standalone and record a rejected candidate in diagnostics.

### 7.2. Epigraph-attribution grouping

Rules:

1. if a paragraph with `structural_role="epigraph"` is immediately followed by a paragraph with `structural_role="attribution"`, create one grouped relation;
2. if AI structure recognition is unavailable, deterministic fallback heuristics may use alignment, length, dash-prefix, style name, and capitalization signals, but only for high-confidence cases;
3. do not group when intervening body/list/caption/image/table paragraphs break adjacency;
4. do not merge text; both paragraphs remain distinct logical paragraphs.

### 7.3. TOC region grouping

Rules:

1. a `toc_header` followed by one or more `toc_entry` paragraphs becomes one `toc_region` relation;
2. a contiguous run of `toc_entry` paragraphs without an explicit header may still form a `toc_region` when the run length and entry pattern are high-confidence;
3. any non-TOC paragraph breaks the region;
4. relation normalization groups the region for chunking and diagnostics, but does not by itself define whether later phases skip editing or rewrite the TOC.

## 8. Consumer Changes

### 8.1. Semantic block construction

`build_semantic_blocks()` should become relation-aware rather than hard-coding only asset-caption adjacency.

Required behavior:

1. a relation cluster should not be split across block boundaries unless a protected hard limit makes that impossible;
2. captions should stay with their anchored image/table block;
3. epigraph-attribution pairs should stay in the same block;
4. TOC regions should stay contiguous in one block unless size constraints force a documented fallback.

### 8.2. Rendering and editing jobs

Phase 2 does not require a new markdown syntax, but downstream job-building must preserve relation adjacency.

Required behavior:

1. paragraph markers remain one per paragraph;
2. relation metadata may influence which paragraphs are scheduled into the same job;
3. context-window extraction should avoid separating closely related members when the relation is explicit.

### 8.3. Formatting diagnostics and validation

Formatting diagnostics and structural validation should surface relation outcomes directly.

Additions:

1. per-paragraph diagnostic entries may include `relation_ids`;
2. aggregate metrics should include counts by relation kind;
3. real-document structural validation should report relation counts and rejected-candidate counts.

## 9. Diagnostics Artifacts

Add a dedicated relation-normalization diagnostics artifact, analogous to the Phase 1 boundary report.

Suggested location:

1. `.run/relation_normalization_reports/` for ad hoc/debug artifacts;
2. run-scoped real-document artifacts should include relation summary data in the current manifest/report outputs.

Suggested artifact payload:

1. source filename and short source hash;
2. enabled relation kinds;
3. accepted relations with paragraph ids, relation kind, anchor asset id, and rationale;
4. rejected candidates with reasons;
5. aggregate counts.

## 10. Implementation Slices

### 10.1. Slice 1: relation model and detection engine

Files:

1. `models.py`
2. `document.py`
3. targeted tests

Tasks:

1. add relation dataclasses and deterministic detection helpers;
2. build a relation-normalization result/report over `ParagraphUnit` lists;
3. preserve compatibility fields such as `attached_to_asset_id`.

### 10.2. Slice 2: relation-aware semantic blocks

Files:

1. `document.py`
2. `document_pipeline.py` if block/job plumbing requires it
3. targeted tests

Tasks:

1. update semantic block formation to honor relation clusters;
2. remove narrow hard-coded rules that become redundant under the shared relation model;
3. preserve current behavior for documents with no accepted relations.

### 10.3. Slice 3: diagnostics and validation

Files:

1. `formatting_transfer.py`
2. `real_document_validation_structural.py`
3. targeted tests

Tasks:

1. serialize relation metadata and aggregate counts into diagnostics;
2. expose relation metrics in real-document structural validation;
3. keep reports stable and user-inspectable.

## 11. Verification Criteria

Phase 2 implementation is acceptable only if all of the following are demonstrated:

1. existing Phase 1 merge behavior remains unchanged for false body-paragraph repair;
2. adjacent image/table captions are represented as explicit relations and remain grouped in semantic blocks;
3. epigraph-attribution synthetic fixtures stay grouped without text merge;
4. TOC runs form deterministic regions without swallowing unrelated body paragraphs;
5. marker mode still emits one marker per paragraph;
6. formatting diagnostics and real-document validation expose relation counts;
7. full visible repository pytest and visible Lietaer real validation remain green.

## 12. Approval Gate

This document is the required Phase 2 spec. Because the implementation touches multiple modules and cross-cutting contracts, code changes for Phase 2 should not begin until the user explicitly approves this spec or requests a narrowed subset.