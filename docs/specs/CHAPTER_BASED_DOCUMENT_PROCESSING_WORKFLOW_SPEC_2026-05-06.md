# Chapter-Based Document Processing Workflow Spec

Date: 2026-05-06

## Objective

Transition DocxAICorrector from a monolithic full-document translation workflow to a granular chapter and section based workflow.

After the initial document analysis, the system must present the user with processing statistics and a structured list of detected book chapters or sections. The user must be able to select a single chapter, multiple chapters, or the entire book for later translation and processing.

This removes the need for manual pre-splitting of files and enables incremental translation for phased voice-over production, episodic publication, review cycles, and partial reprocessing.

## Architectural Direction

DocxAICorrector already has the required lower-level execution model:

- Upload normalization in `src/docxaicorrector/processing/processing_runtime.py`.
- Preparation and analysis in `src/docxaicorrector/processing/preparation.py`.
- Paragraph units and structure metadata in `src/docxaicorrector/core/models.py`.
- Structure recognition in `src/docxaicorrector/structure/recognition.py`.
- Semantic block generation in `src/docxaicorrector/document/semantic_blocks.py`.
- Per-block processing in `src/docxaicorrector/pipeline/block_execution.py`.
- Final artifact generation in `src/docxaicorrector/pipeline/late_phases.py` and `src/docxaicorrector/runtime/artifacts.py`.
- Streamlit UI composition in `src/docxaicorrector/ui/_app.py` and `src/docxaicorrector/ui/_ui.py`.

The recommended implementation is to add a first-class `DocumentSegment` layer above the existing semantic block and job layer.

```text
Document
  -> ParagraphUnit[]
  -> DocumentSegment[]      user-facing chapters and sections
  -> DocumentBlock[]        LLM-safe execution chunks
  -> ProcessingJob[]        existing backend job payloads
```

Segments should be the UX and orchestration unit. Semantic blocks should remain the LLM execution unit.

## Parsing And Segment Detection

Add a new module:

```text
src/docxaicorrector/document/segments.py
```

### Proposed Models

```python
@dataclass(frozen=True)
class SegmentBoundaryEvidence:
    source: str  # heading_style, toc_match, page_break, numbering_pattern, ai_structure, fallback
    confidence: str  # high, medium, low
    details: dict[str, object]


@dataclass(frozen=True)
class DocumentSegment:
    segment_id: str
    parent_segment_id: str | None
    ordinal: int
    level: int
    title: str
    normalized_title: str
    start_paragraph_index: int
    end_paragraph_index: int
    start_paragraph_id: str
    end_paragraph_id: str
    paragraph_ids: tuple[str, ...]
    paragraph_count: int
    char_count: int
    word_count: int
    estimated_token_count: int  # Phase 1 heuristic: max(1, char_count // 4)
    structural_role: str  # front_matter, chapter, section, appendix, bibliography, toc, body_range
    confidence: str
    boundary_fingerprint: str
    boundary_evidence: tuple[SegmentBoundaryEvidence, ...]
    warnings: tuple[str, ...] = ()
```

```python
@dataclass(frozen=True)
class SegmentDetectionReport:
    segment_count: int
    high_confidence_count: int
    medium_confidence_count: int
    low_confidence_count: int
    fallback_segment_count: int
    toc_entry_count: int
    toc_matched_count: int
    warnings: tuple[str, ...]
```

```python
@dataclass(frozen=True)
class GlossaryTerm:
    source_term: str
    target_term: str = ""
    confidence: str = "medium"
    source_segment_id: str | None = None


@dataclass(frozen=True)
class SegmentOutlineEntry:
    segment_id: str
    title: str
    level: int
    structural_role: str
```

Phase 1 token estimation can use a deterministic low-cost heuristic:

```text
estimated_token_count = max(1, char_count // 4)
```

### Detection Signals

Run segment detection after extraction, cleanup, relation normalization, structure validation, and optional AI structure recognition.

Detection should combine these signals:

| Priority | Signal | Confidence | Behavior |
|---|---|---|---|
| 1 | Explicit DOCX heading styles | High | Treat `ParagraphUnit.role == "heading"` and `heading_level` as segment boundary |
| 2 | Structure recognition | High or medium | Use AI-promoted headings and `structural_role` metadata |
| 3 | Table of contents | High or medium | Match TOC entries to body headings and infer hierarchy |
| 4 | Numbering patterns | Medium | Detect `Chapter 1`, `Глава 1`, `Part I`, `Section 2.3`, roman numerals |
| 5 | Page or section breaks | Low or medium | Use only as supporting evidence unless paired with heading-like text |
| 6 | Typography | Low or medium | Centered, bold, all-caps, large-font short paragraphs |
| 7 | Fallback segmentation | Low | Split by size and natural paragraph boundaries when no reliable structure exists |

Fallback segmentation must use an explicit size contract rather than an abstract "split by size" rule.

Recommended Phase 1 rule:

```text
fallback_segment_max_chars = max(chunk_size * 4, 24000)
```

Fallback splitting should prefer the nearest safe boundary after a paragraph that is not inside a table/image atomic unit and is not a TOC cluster continuation.

### Detection Algorithm

```text
1. Build paragraph descriptors from prepared ParagraphUnit objects.
2. Identify TOC regions using existing structural roles such as toc_header and toc_entry.
3. Extract TOC candidates with title, optional page number, and hierarchy hints.
4. Identify boundary candidates from headings, numbering, typography, and page/section breaks.
5. Match TOC entries to candidate headings by reusing the existing TOC title normalization and fuzzy-prefix logic from `src/docxaicorrector/document/structure_repair.py`, especially `_collect_toc_title_variants()` and related matching helpers, instead of inventing a second independent matcher.
6. Assign segment levels from heading_level, numbering depth, TOC indentation, or inferred hierarchy.
7. Build a segment tree with parent and child links.
8. Mark front matter, TOC, body chapters, appendices, bibliography, and synthetic fallback ranges.
9. Clamp segment ranges to paragraph boundaries.
10. Validate that every paragraph belongs to exactly one leaf segment.
11. Split overlarge segments into synthetic child segments only when required by processing limits.
12. Return segment tree plus diagnostics for the analysis screen.
```

### Hard Boundaries For Semantic Blocks

`build_semantic_blocks()` should accept optional hard paragraph boundaries so LLM jobs do not cross chapter boundaries.

```python
def build_semantic_blocks(
    paragraphs: list[ParagraphUnit],
    max_chars: int = 6000,
    *,
    relations: list[ParagraphRelation] | None = None,
    hard_boundary_paragraph_ids: set[str] | None = None,
) -> list[DocumentBlock]:
    ...
```

This is important because later partial processing must be able to select chapter-owned jobs without accidental bleed into another chapter.

## Prepared Data Contract

Extend `PreparedDocumentData` in `src/docxaicorrector/processing/preparation.py`:

```python
@dataclass
class PreparedDocumentData:
    source_text: str
    paragraphs: list
    image_assets: list
    relations: list[ParagraphRelation]
    jobs: list[dict[str, Any]]
    segments: list[DocumentSegment]
    segment_diagnostics: SegmentDetectionReport
    structure_fingerprint: str
    detector_version: str
    prepared_source_key: str
    ...
```

Preparation should produce:

- `paragraphs`
- `relations`
- `structure_map`
- `segments`
- `segment_diagnostics`
- `structure_fingerprint`
- `detector_version`
- `semantic_blocks`
- `jobs`
- `segment_to_job` mapping
- high-level analysis statistics

### PreparedRunContext Extension

The UI layer does not consume `PreparedDocumentData` directly. It consumes `PreparedRunContext` from `src/docxaicorrector/ui/application_flow.py`, which is created by mapping fields from `PreparedDocumentData` inside `_build_prepared_run_context(...)` and then transported through `PreparationCompleteEvent`.

Therefore the same segment-related fields must also be added to `PreparedRunContext`:

```python
@dataclass
class PreparedRunContext:
    ...
    segments: list[DocumentSegment]
    segment_diagnostics: SegmentDetectionReport
    structure_fingerprint: str
    detector_version: str
```

Required implementation rule:

```text
PreparedDocumentData -> PreparedRunContext mapping must copy all segment-related fields.
The analysis screen and chapter selector must read from PreparedRunContext, not from PreparedDocumentData.
```

## State Model

Do not introduce a database-backed persistent state model for the first implementation.

The intended user model is session scoped: each fresh upload starts a new analysis and clears prior processing statuses. The user is expected to know which chapter was translated in a previous session and select the next chapter manually.

The core requirement is therefore not durable processing state. The core requirement is **verifiable and reproducible structure detection**.

### Session State

Keep runtime state in Streamlit/session memory and existing run artifacts:

- detected segments for the current uploaded document;
- selected segment IDs;
- active processing status for selected segments;
- completed outputs for the current session;
- structure confirmation state;
- exported structure manifest path when generated.

Recommended in-session statuses:

```text
pending
selected
queued
processing
completed
failed
skipped
```

Avoid `stale` in the first implementation because cross-session staleness is not tracked.

### Structure Manifest

After analysis, allow the user to export the detected structure as a lightweight JSON manifest. This is not a processing database. It is a reproducibility and audit artifact.

Suggested path pattern:

```text
.run/structure_manifests/<timestamp>_<source_stem>.segments.json
```

Manifest fields:

```json
{
  "schema_version": 1,
  "source_name": "book.docx",
  "source_content_hash16": "0123abcd4567ef89",
  "prepared_source_key": "...",
  "detector_version": "chapter_segments_v1",
  "detector_config": {
    "chunk_size": 12000,
    "structure_recognition_mode": "...",
    "min_confidence": "medium"
  },
  "structure_fingerprint": "...",
  "summary": {
    "paragraph_count": 312,
    "segment_count": 22,
    "toc_entry_count": 18,
    "toc_matched_count": 17,
    "low_confidence_count": 1
  },
  "segments": [
    {
      "segment_id": "seg_0003_a1b2c3d4",
      "ordinal": 3,
      "level": 1,
      "title": "Chapter 1: The Signal",
      "normalized_title": "chapter 1 the signal",
      "start_paragraph_index": 42,
      "end_paragraph_index": 79,
      "start_paragraph_id": "p0042",
      "end_paragraph_id": "p0079",
      "paragraph_count": 38,
      "word_count": 4210,
      "confidence": "high",
      "boundary_fingerprint": "...",
      "evidence": [
        {
          "source": "heading_style",
          "confidence": "high",
          "details": {
            "heading_level": 1,
            "style_name": "Heading 1"
          }
        }
      ]
    }
  ]
}
```

The manifest lets the user and developer verify what was detected, compare future detections, and diagnose structure changes without introducing full persistent job state.

### Stable Segment IDs

Segment IDs must be deterministic for the same source document and same detected structure.

Recommended format:

```text
seg_<ordinal_zero_padded>_<hash8>
```

Hash input:

```text
source_content_hash16
normalized_title
level
start_paragraph_id
end_paragraph_id
start_paragraph_index
end_paragraph_index
detector_version
```

This means a repeated analysis of the same file should produce the same segment IDs as long as the structure is unchanged. If IDs change, the UI can clearly show that the detected structure changed.

### Boundary Fingerprint

`boundary_fingerprint` must be deterministic for the same detected segment boundary.

Recommended Phase 1 rule:

```text
boundary_fingerprint = sha1(
  f"{normalized_title}|{level}|{start_paragraph_id}|{end_paragraph_id}"
)[:8]
```

This fingerprint is segment-local and is intended for structure comparison and manifest auditing. It does not replace `segment_id`, which also includes source identity and detector version inputs.

### Structure Fingerprint

Compute a document-level `structure_fingerprint` from the ordered list of segment boundary fingerprints.

Example input:

```text
segment_id | level | normalized_title | start_paragraph_id | end_paragraph_id
```

If the same source document is analyzed again and the fingerprint differs, show a warning:

```text
Detected chapter structure differs from the previously exported structure manifest.
Review the chapter list before processing.
```

The first implementation does not need to automatically remember the previous manifest. The user can upload or compare against an exported manifest in a later phase. At minimum, the UI should display and export the fingerprint.

## Processing Pipeline

The backend should continue processing existing jobs. Segment selection should decide which jobs are included in a run.

### Segment Selection Contract

```python
@dataclass(frozen=True)
class SegmentSelection:
    selected_segment_ids: tuple[str, ...]
    include_descendants: bool = True
    include_front_matter: bool = False
    include_toc: bool = False
    output_mode: str = "selected_only"  # selected_only, selected_with_context, hybrid_document, final_translated_book
```

Output mode precedence rules:

```text
1. `selected_only` ignores `include_front_matter` and `include_toc` and outputs exactly the selected segment set.
2. `selected_with_context` may include front matter and TOC according to `include_front_matter` and `include_toc`.
3. `hybrid_document` and `final_translated_book` are full-document modes and therefore ignore `include_front_matter` and `include_toc` as selection filters.
```

### Processing Flow

```text
1. User selects segments in the UI.
2. UI resolves selected segment IDs to paragraph ID ranges.
3. Backend resolves jobs whose paragraph IDs are inside selected ranges.
4. Backend preserves context_before and context_after from the surrounding document, but emits output only for selected jobs.
5. Existing block execution processes selected jobs.
6. Segment and job statuses are updated in session state after every job.
7. Partial artifacts are saved per selected segment or selected segment bundle.
8. Reassembly builds selected-only, hybrid, or final outputs depending on output mode.
```

Job inclusion rule:

```text
Include a job if all output paragraph IDs belong to selected segment coverage.
```

If cached jobs predate segment hard boundaries, invalidate and rebuild jobs.

### Full-Book Processing Path

The system must preserve the existing monolithic processing path as a first-class execution mode.

Rules:

```text
1. Full-book processing does not require `structure_confirmed = true`.
2. Full-book processing does not depend on `selected_segment_ids`.
3. Full-book processing reuses the existing prepared document and legacy/full-book job set.
4. Full-book processing is the safe fallback when chapter detection is ambiguous or unacceptable.
```

### Processing Context Changes

Extend `ProcessingContext` in `src/docxaicorrector/pipeline/contracts.py`:

```python
@dataclass(frozen=True)
class ProcessingContext:
    ...
    selected_segment_ids: Sequence[str] | None = None
    document_segments: Sequence[DocumentSegment] = ()
    segment_selection_mode: str = "all"
    output_mode: str = "selected_only"
```

Extend `ProcessingState`:

```python
@dataclass
class ProcessingState:
    processed_chunks: list[str]
    narration_chunks: list[str]
    generated_paragraph_registry: list[dict[str, object]]
    segment_outputs: dict[str, list[str]] = field(default_factory=dict)
    completed_segment_ids: set[str] = field(default_factory=set)
    failed_segment_ids: set[str] = field(default_factory=set)
```

## Queue And Runtime Events

The current background worker and event queue can remain.

Phase 1 should prefer the lower-risk option: reuse existing `SetStateEvent` and `SetProcessingStatusEvent` payloads for segment-aware progress rather than introducing a brand new event family immediately.

If dedicated event dataclasses are introduced later, recommended names are:

```text
SegmentQueuedEvent
SegmentStartedEvent
SegmentProgressEvent
SegmentCompletedEvent
SegmentFailedEvent
SegmentArtifactSavedEvent
```

Mandatory typing rule if dedicated events are added:

```text
Update the ProcessingEvent type union in src/docxaicorrector/runtime/events.py to include every new Segment*Event type.
```

Progress semantics:

```text
Document run progress = completed selected jobs / total selected jobs
Segment progress = completed jobs in segment / total jobs in segment
Session book progress = completed segments in current session / total detected segments
```

Default processing policy:

```text
Process selected segments sequentially.
Continue on segment failure.
Save artifacts for completed selected segments.
Retry failed jobs only when possible.
Do not imply cross-session completion state unless a future persistent state feature is added.
```

## Context Preservation

Partial processing must retain document-level consistency.

Add a document context profile generated during analysis:

```python
@dataclass(frozen=True)
class DocumentContextProfile:
    source_token: str
    structure_fingerprint: str
    source_title: str | None
    detected_author: str | None
    source_language: str
    target_language: str
    translation_domain: str
    style_instructions: str
    glossary_terms: tuple[GlossaryTerm, ...]
    segment_outline: tuple[SegmentOutlineEntry, ...]
```

Each segment prompt should include:

- Global document style guide.
- Approved glossary and translation memory.
- Book outline.
- Current chapter title and position.
- Previous completed segment summary.
- Next segment title or brief context.
- Existing local `context_before` and `context_after`.

Avoid including too much raw text from other chapters. Prefer summaries and glossary terms to reduce token pressure.

## Reassembly

Add a reassembly service:

```text
src/docxaicorrector/document/reassembly.py
```

Responsibilities:

- Load original paragraph order.
- Load processed paragraph registry and output for completed segments.
- Use source paragraphs for unprocessed segments when requested.
- Generate Markdown in original order.
- Convert Markdown to DOCX using the existing Pandoc path.
- Preserve paragraph properties using the existing generated paragraph registry.
- Reinsert images through the existing image behavior.
- Write a manifest with segment coverage.

### Reassembly Modes

| Mode | Use Case | Output |
|---|---|---|
| `selected_only` | Voice-over chapter export | DOCX and Markdown only for selected chapters |
| `selected_with_context` | Episodic publication with context | Optional title/front matter plus selected chapters |
| `hybrid_document` | Incremental translation review | Full document with completed segments translated and pending segments kept as original source text |
| `final_translated_book` | Final book output | Full translated document, enabled only when all required segments are complete in the current session |

### Reassembly Manifest Example

```json
{
  "source_token": "upload_...",
  "structure_fingerprint": "...",
  "run_id": "run_...",
  "source_name": "book.docx",
  "output_mode": "selected_only",
  "coverage": {
    "segment_ids": ["seg_003"],
    "paragraph_ranges": [[120, 188]]
  },
  "segments": [
    {
      "segment_id": "seg_003",
      "title": "Chapter 3: The Boundary",
      "status": "completed",
      "markdown_path": ".run/ui_results/...",
      "docx_path": ".run/ui_results/..."
    }
  ]
}
```

## UI/UX Design

The analysis result screen should appear after preparation completes and before processing starts.

The primary UX challenge is not tracking historical completion across sessions. The primary challenge is giving the user confidence that detected chapters are correct and that repeated analysis of the same file will not silently change the structure.

### Workflow State Contract

Do not add a new `ProcessingOutcome` enum value for the analysis screen.

The current `ProcessingOutcome` enum in `src/docxaicorrector/runtime/workflow_state.py` should remain focused on run lifecycle: `IDLE`, `RUNNING`, `STOPPED`, `FAILED`, `SUCCEEDED`.

The intermediate UI state "Analysis Complete + Chapter Selector" must be represented by session-state flags layered on top of an already prepared `PreparedRunContext`, for example:

```text
structure_confirmed
confirmed_structure_fingerprint
confirmed_at_settings_hash
selected_segment_ids
segments_loaded_for_source_token
```

Implementation rule:

```text
Analysis-review state is a session/UI concern, not a new processing outcome.
```

### Analysis Result Screen Layout

```text
+---------------------------------------------------------------------+
| Analysis Complete                                                    |
| book.docx · 74,221 words · 18 chapters · 312 paragraphs · 12 images |
+-------------------------------+-------------------------------------+
| Statistics                    | Chapter Selector                    |
|                               |                                     |
| Words: 74,221                 | [ ] Entire book                     |
| Characters: 421,900           |                                     |
| Paragraphs: 312               | Front Matter                        |
| Images: 12                    | [ ] Preface                         |
| Chapters: 18                  | [ ] Introduction                    |
| Est. blocks: 96               |                                     |
| Est. cost/time: ...           | Part I                              |
| Structure confidence: High    | [x] Chapter 1 - The Signal          |
| TOC matched: 17/18            | [x] Chapter 2 - Production Boundary |
| Warnings: 1                   | [ ] Chapter 3 - Value Theory        |
|                               |                                     |
| Quality / Structure           | Appendices                          |
| [pass] Boundary normalization | [ ] Appendix A                      |
| [warn] One low-confidence h.  | [ ] Bibliography                    |
+-------------------------------+-------------------------------------+
| Selection Summary                                                    |
| 2 chapters selected · 8,921 words · approx. 11 LLM blocks            |
|                                                                     |
| [Confirm Structure] [Process Selected] [Process Entire Book]         |
| [Export Structure Manifest]                                          |
+---------------------------------------------------------------------+
```

Phase 1 clarification:

```text
Until Phase 2 segment-aware job filtering is implemented, `Process Selected` should be visible but disabled, with a tooltip or inline note that chapter-based execution becomes available in Phase 2.
Phase 1 may render the selection UI and structure confirmation flow, but full-book processing remains the only executable processing path.
`Process Entire Book` must remain available as the explicit legacy/full-book action.
```

Status update 2026-05-06:

```text
Minimal early Phase 2 filtering is now implemented for selected chapters only.
`Process Selected` is enabled only after structure confirmation and only when the current selection resolves to a non-empty job set.
This path currently produces a partial result artifact from the filtered job/paragraph subset and does not yet include segment-level progress/status families.
`Process Entire Book` remains the explicit legacy/full-book fallback path.
```

Use Streamlit native primitives where possible:

| UI Area | Streamlit Primitive |
|---|---|
| Summary cards | `st.columns()` |
| Selector panel | `st.container()` |
| Tree rows | Checkbox rows with indentation |
| Diagnostics | `st.expander()` |
| Selection summary | `st.info()` |
| Actions | `st.button()` in columns |

### Chapter Selector Behavior

The selector should support:

- Select entire book.
- [x] Select or deselect parent section with descendants using the current flat checkbox list, without introducing a nested tree UI model yet.
- [x] Show minimal flat-list relationship hints for parent/child rows, including descendant count on parent rows and parent title on child rows.
- [x] Show minimal flat-list level awareness in the selector, with lightweight indentation/prefixing for nested rows and a compact visible-structure summary.
- [x] Show a more explicit confirmation/selection summary in the analysis panel, including confirmed fingerprint context and top-level vs nested selection counts.
- [x] Show lightweight last-exported-manifest comparison messaging in the analysis panel when the current fingerprint differs from the most recently exported manifest in the current session.
- [x] Selection changes no longer clear `structure_confirmed`; confirmation is preserved across chapter selection changes and is only invalidated by fingerprint or settings changes.
- [x] Selection info line shows selected/total counts for segments, words, and jobs (e.g. `Selected: 2/5 segments | 400/1200 words | approx. 3/8 jobs`).
- [x] Confirm Structure button shows "Re-confirm Structure" label when structure is already confirmed, making the re-confirmation action explicit.
- [x] Action button area shows explicit "Ready: confirmed structure | selection resolves to processable jobs." caption when `Process Selected` is enabled; shows specific unavailable reason when disabled.
- [x] Select a single chapter.
- [x] Select multiple non-contiguous chapters.
- [x] Select entire book (via "Select Entire Book" bulk action).
- [x] Filter by pending, failed, completed, skipped, or low confidence.
- [x] Search by title.
- [x] Show word count and estimated processing blocks per segment.
- [x] Show confidence badge.
- [x] Show status badge.
- [x] Show warnings for low-confidence boundaries.
- [x] Preview start and end text for each detected chapter.
- [x] Show boundary evidence for each chapter.
- [x] Require structure confirmation before processing selected chapters.
- [x] Export the detected structure manifest.

### Structure Verification UX

Add a required verification step between analysis and processing.

Recommended UI elements:

| Element | Purpose |
|---|---|
| `Structure fingerprint` | Shows a stable hash for the detected outline |
| `Detector version` | Makes structure changes traceable after code/config changes |
| `Confidence summary` | Shows high/medium/low chapter boundary counts |
| `TOC match score` | Shows how many TOC entries matched body headings |
| `Boundary preview` | Shows the first and last paragraph preview for each chapter |
| `Evidence expander` | Explains why the boundary was detected |
| `Confirm Structure` button | Freezes the current in-session outline for processing |
| `Process Entire Book` button | Runs the existing monolithic full-book pipeline without depending on chapter selection |
| `Export Structure Manifest` button | Lets user save the outline for later comparison/audit |

### Action Button Behavior

#### `Confirm Structure`

Purpose:

- freezes the full currently detected outline for the current session, independent of search/filter state in the UI;
- stores `confirmed_structure_fingerprint` in session state;
- stores a snapshot hash of detection-affecting settings in session state as `confirmed_at_settings_hash`;
- marks `structure_confirmed = true`;
- allows subsequent processing actions to use the confirmed segment list rather than a recomputed one.

When the button is clicked:

```text
1. Validate that a detected segment list exists for the active source_token.
2. Validate that every segment in the full detected outline has a deterministic segment_id and boundary_fingerprint.
3. Save confirmed_structure_fingerprint in session state.
4. Save a settings snapshot hash for all detection-affecting settings as `confirmed_at_settings_hash`.
5. Save the full confirmed segment list for the current source_token in session state.
6. Enable processing actions that depend on confirmed structure.
```

The button does not:

- write translation outputs;
- start translation;
- persist cross-session completion state;
- silently re-run structure detection.

If structure changes after confirmation:

```text
1. Invalidate structure_confirmed.
2. Show a warning banner.
3. Disable segment-based processing until the user confirms the new structure again.
```

Semantics note:

```text
`Confirm Structure` always applies to the full detected outline for the active source_token.
It is not a partial confirmation of only the currently filtered or manually highlighted subset.
```

#### `Export Structure Manifest`

Purpose:

- writes the currently detected structure to `.run/structure_manifests/...segments.json`;
- gives the user a stable audit artifact showing what the system recognized;
- allows later manual comparison between repeated analyses of the same file.

When the button is clicked:

```text
1. Serialize the currently displayed structure.
2. Include source metadata, detector_version, structure_fingerprint, summary, and ordered segment list.
3. Save the manifest to `.run/structure_manifests/`.
4. Show the saved manifest path and fingerprint in the UI.
```

The button does not:

- confirm the structure automatically;
- enable processing by itself;
- alter selected chapters;
- act as a source of truth over the live UI state.

Export is primarily for verification, audit, debugging, and side-by-side comparison of repeated analyses.

#### `Process Entire Book`

Purpose:

- starts the existing full-book processing path;
- bypasses chapter selection as an execution requirement;
- remains available even when the user does not trust detected chapter structure.

When the button is clicked:

```text
1. Use the already prepared source document and existing full-book jobs.
2. Ignore selected chapter checkboxes as an execution filter.
3. Start the current legacy/full-book processing flow.
4. Show standard run progress and final full-book artifacts.
```

The button does not:

- require `structure_confirmed = true`;
- depend on selected segments;
- claim that detected chapter boundaries were accepted by the user.

Recommended UX rule:

```text
`Process Entire Book` is the safe fallback when chapter detection is incomplete, ambiguous, or visibly wrong.
```

Chapter row concept:

```text
[ ] Chapter 3: Why Value Theory Matters
    5,020 words · 7 blocks · confidence: high · source: TOC + Heading 1
    Starts: "Why value theory matters..."
    Ends:   "...the next chapter turns to institutional feedback."
    Boundary ID: seg_0003_a1b2c3d4
```

Low-confidence row concept:

```text
[ ] Chapter 7: Untitled section
    3,840 words · 5 blocks · confidence: low · source: typography fallback
    Warning: no explicit heading style or TOC match found.
    Review before processing.
```

### What The User Does If Structure Does Not Match The Book

The UI must not assume the detected structure is always correct. If the user sees that chapter boundaries, titles, nesting, or omitted sections do not match the real book, the expected actions are:

```text
1. Do not confirm the structure yet.
2. Expand the suspicious chapter rows and inspect boundary previews and evidence.
3. Export the structure manifest if the user wants an audit snapshot or needs to compare multiple attempts.
4. Adjust analysis-affecting settings if available, then re-run analysis.
5. Review the new structure_fingerprint and updated chapter tree.
6. Confirm structure only after the visible chapter map is acceptable.
```

Examples of user-visible mismatch cases:

- one chapter was split into two segments incorrectly;
- several short sections were merged into one chapter;
- front matter or bibliography was treated as body chapters;
- TOC matched the wrong body heading;
- PDF-derived layout noise created false boundaries.

### Recovery Actions When Structure Is Wrong

If the structure is visibly wrong, the UI should guide the user toward one of these actions:

| User action | Intended outcome |
|---|---|
| Review boundary previews | Verify whether the detected start/end paragraphs are acceptable |
| Expand evidence details | Understand why a segment boundary was created |
| Re-run analysis | Recompute segments after changing relevant settings |
| Export structure manifest | Save the current faulty or candidate structure for comparison |
| Use full-book processing fallback | Continue without chapter selection if chapter segmentation is not trustworthy yet |

Phase 1 and early Phase 2 rule:

```text
If the user does not trust the detected chapter structure, the safe fallback is to avoid segment-based processing and use the existing full-book processing path.
```

### Re-Analysis UX When Structure Changes

If the user re-runs analysis and the new structure differs from the previously viewed or confirmed one, the UI should show a visible warning such as:

```text
Detected chapter structure changed after re-analysis.
Previous fingerprint: 8fd1c2...
Current fingerprint:  a91be7...
Review the updated chapter list before processing.
```

Expected user flow after this warning:

```text
1. Compare the new chapter tree with the book.
2. Inspect the chapters whose boundaries changed.
3. Re-confirm structure if the new outline is acceptable.
4. If still unacceptable, export the manifest and either re-run analysis again or fall back to full-book processing.
```

### Settings Change Detection After Confirmation

The UI must be able to detect when detection-affecting settings changed after structure confirmation.

Required mechanism:

```text
1. At confirmation time, compute and store `confirmed_at_settings_hash` in session state.
2. The hash must include all settings that can affect structure detection.
3. On every rerun, recompute the current settings hash.
4. If the current hash differs from `confirmed_at_settings_hash`, invalidate `structure_confirmed`.
5. Show a warning that the confirmed structure is no longer valid for the current settings.
```

Minimum hash inputs:

- uploaded source token;
- structure recognition mode;
- paragraph boundary normalization mode;
- minimum heading confidence;
- detector version;
- PDF/DOC conversion-relevant settings;
- chunk size only if synthetic oversized-segment splitting depends on it.

### Structure Stability Rules

Before allowing processing:

```text
1. The user must confirm the detected structure in the current session.
2. Processing uses the confirmed in-session segment list, not a recomputed segment list.
3. If settings that affect structure detection change, invalidate confirmation and require review again.
4. If the same uploaded source is re-analyzed in the same session, compare structure_fingerprint values.
5. If fingerprints differ, show a warning and require explicit confirmation again.
```

Settings that should invalidate structure confirmation:

- uploaded source bytes changed;
- structure recognition mode changed;
- paragraph boundary normalization mode changed;
- PDF/DOC conversion output changed;
- detector version changed;
- minimum heading confidence changed;
- chunking settings changed only if synthetic oversized-segment splitting depends on chunk size.

### Status Visuals

| Status | Visual | Behavior |
|---|---|---|
| `pending` | Gray badge | Selectable |
| `queued` | Blue outline badge | Locked while queued |
| `processing` | Blue spinner or progress bar | Locked |
| `completed` | Green badge | Selectable for reprocess or export |
| `failed` | Red badge | Selectable for retry |
| `skipped` | Muted badge | Usually excluded by default |

### Interaction Flow

```text
Upload document
  -> Normalize DOCX/DOC/PDF
  -> Prepare and analyze document
  -> Detect chapters and sections
  -> Show Analysis Complete screen
  -> User reviews detected structure, boundary previews, and confidence
  -> User confirms structure
  -> User selects segments
  -> User chooses output mode
  -> Trigger partial translation
  -> Show segment-level progress
  -> Save partial artifacts
  -> Return to selector with updated statuses
  -> User processes more chapters or builds final book
```

### Streamlit State

Recommended session state keys:

```text
selected_segment_ids
expanded_segment_ids
segment_status_by_id
active_source_token
confirmed_structure_fingerprint
confirmed_at_settings_hash
structure_confirmed
chapter_selector_filter
chapter_selector_search
reassembly_mode
```

Recommended additional key:

```text
segments_loaded_for_source_token
```

Status note for setting changes:

```text
Changing language, processing operation, or other non-detection runtime settings does not automatically rewrite existing in-session `completed` segment statuses.
Those statuses remain a record of what was completed earlier in the same session, and any semantic mismatch between earlier artifacts and new settings is visible responsibility of the user until a future stale-status feature is introduced.
```

The selector should remain visible after a run completes so the user can continue processing the next chapter without re-uploading or manually splitting the source file.

## API Requirements

These contracts can be implemented first as internal service calls and later exposed as HTTP endpoints.

### Analyze Document

```http
POST /api/documents/analyze
```

Request:

```json
{
  "source_token": "upload_...",
  "chunk_size": 12000,
  "processing_operation": "translate",
  "source_language": "en",
  "target_language": "ru",
  "translation_domain": "theology",
  "image_mode": "safe"
}
```

Response:

```json
{
  "source_token": "upload_...",
  "analysis_status": "completed",
  "structure_fingerprint": "...",
  "detector_version": "chapter_segments_v1",
  "statistics": {
    "paragraph_count": 312,
    "segment_count": 22,
    "block_count": 96,
    "image_count": 12,
    "word_count": 74221,
    "source_chars": 421900
  },
  "segment_detection": {
    "confidence": "high",
    "toc_entry_count": 18,
    "toc_matched_count": 17,
    "warnings": ["One TOC entry was not matched to a body heading"]
  },
  "segments": [
    {
      "segment_id": "seg_001",
      "parent_segment_id": null,
      "ordinal": 1,
      "level": 1,
      "title": "Front Matter",
      "status": "pending",
      "word_count": 2411,
      "estimated_block_count": 4,
      "confidence": "high"
    }
  ]
}
```

### Get Document Segments

```http
GET /api/current-analysis/segments
```

Response:

```json
{
  "source_token": "upload_...",
  "structure_fingerprint": "...",
  "structure_confirmed": true,
  "segments": [],
  "status_summary": {
    "pending": 18,
    "processing": 1,
    "completed": 2,
    "failed": 1
  }
}
```

### Confirm Detected Structure

```http
POST /api/current-analysis/structure/confirm
```

Request:

```json
{
  "source_token": "upload_...",
  "structure_fingerprint": "...",
  "confirmed_segment_ids": ["seg_0001_...", "seg_0002_...", "seg_0003_..."],
  "confirmed_at_settings_hash": "..."
}
```

Semantics:

```text
`confirmed_segment_ids` is not a partial-selection mechanism.
It is the ordered full-outline segment ID list that the client saw at confirmation time and sends back as a verification payload.
If the server-side detected outline and the provided full list differ, confirmation must be rejected and the user must review the structure again.
```

Response:

```json
{
  "structure_confirmed": true,
  "confirmed_structure_fingerprint": "..."
}
```

### Export Structure Manifest

```http
POST /api/current-analysis/structure/export
```

Response:

```json
{
  "manifest_path": ".run/structure_manifests/20260506_083400_book.segments.json",
  "structure_fingerprint": "...",
  "segment_count": 22
}
```

### Start Segment Processing

```http
POST /api/current-analysis/runs
```

Request:

```json
{
  "selected_segment_ids": ["seg_003", "seg_004"],
  "confirmed_structure_fingerprint": "...",
  "include_descendants": true,
  "processing_operation": "translate",
  "output_mode": "selected_only",
  "source_language": "en",
  "target_language": "ru",
  "translation_domain": "theology",
  "model_selector": "default",
  "max_retries": 2,
  "continue_on_segment_failure": true
}
```

Response:

```json
{
  "run_id": "run_...",
  "status": "queued",
  "selected_segment_count": 2,
  "selected_job_count": 13
}
```

Clarification:

```text
`output_mode` in `/api/current-analysis/runs` determines how artifacts should be assembled after the run completes.
Precondition enforcement for `final_translated_book` applies at the reassemble step, not at run creation.
```

### Get Run Status

```http
GET /api/runs/{run_id}
```

Response:

```json
{
  "run_id": "run_...",
  "source_token": "upload_...",
  "status": "processing",
  "progress": {
    "completed_jobs": 7,
    "total_jobs": 13,
    "completed_segments": 1,
    "total_segments": 2
  },
  "segments": [
    {
      "segment_id": "seg_003",
      "title": "Chapter 1",
      "status": "completed",
      "progress": 1.0
    },
    {
      "segment_id": "seg_004",
      "title": "Chapter 2",
      "status": "processing",
      "progress": 0.57
    }
  ]
}
```

Stopped-run status rule:

```text
If a run ends with STOPPED, segments with status `queued` or `processing` must revert to `pending`.
Segments already marked `completed` or `failed` keep their status.
```

### Retry Failed Segments

```http
POST /api/runs/{run_id}/retry
```

Request:

```json
{
  "segment_ids": ["seg_009"],
  "retry_failed_jobs_only": true
}
```

Response:

```json
{
  "run_id": "run_retry_...",
  "status": "queued"
}
```

Phase gating rule:

```text
Retry UI and retry API are Phase 3 capabilities.
Before Phase 3, failed segments may be shown in the UI, but retry controls should be visible and disabled, or omitted entirely.
```

Current implementation note:

```text
The current Streamlit chapter review flow now implements a minimal Phase 3 `Retry Failed` action that reruns failed segments from the current session through the existing selected-segment processing path. Job-level failed-job-only reuse remains a later refinement.
```

### Start Full-Book Processing

```http
POST /api/current-analysis/full-book-run
```

Request:

```json
{
  "processing_operation": "translate",
  "source_language": "en",
  "target_language": "ru",
  "translation_domain": "theology",
  "model_selector": "default",
  "max_retries": 2
}
```

Response:

```json
{
  "run_id": "run_full_...",
  "status": "queued",
  "mode": "full_book"
}
```

Contract:

```text
This endpoint runs the existing full-book processing path.
It ignores chapter selection and does not require `structure_confirmed = true`.
```

### Reassemble Artifacts

```http
POST /api/current-analysis/artifacts/reassemble
```

Request:

```json
{
  "output_mode": "final_translated_book",
  "segment_ids": "all_completed",
  "include_original_for_pending": false
}
```

Precondition guard:

```text
`final_translated_book` is allowed only when all required segments are completed in the current session.
Required segments = all detected segments except those explicitly marked `skipped` by design, such as TOC or bibliography when excluded by the active workflow rules.
If the precondition is not satisfied, the UI must disable this action and the API must return a validation error.
```

Response:

```json
{
  "artifact_id": "artifact_...",
  "status": "completed",
  "markdown_path": ".run/ui_results/...",
  "docx_path": ".run/ui_results/...",
  "manifest_path": ".run/ui_results/..."
}
```

## Error Handling

Failures must be isolated at job and segment level.

Rules:

- Job failure must not discard completed jobs in the same segment.
- Segment failure must not fail unrelated selected segments unless `fail_fast` is enabled.
- Run failure summary must list failed segments and failed jobs.
- Retry should target failed jobs only when possible.
- Partial outputs from completed segments must remain downloadable.
- Completed segment outputs are only tracked in the current session and by saved artifacts.
- If a run ends with `STOPPED`, segments still in `queued` or `processing` revert to `pending`.
- Segments already marked `completed` or `failed` keep their status after `STOPPED`.

UI behavior:

- Failed chapter shows a red badge.
- Expandable error details show failed block index, error code, retry count, and last message.
- Retry button is now available in the chapter review panel and reruns failed segments from the current session through the existing selected-segment path; later refinements may narrow this further to failed jobs only when enough per-job retry state exists.
- The chapter selector remains available after failure.

## Edge Cases

| Edge Case | Handling |
|---|---|
| No headings detected | Create fallback segments by size and paragraph boundaries |
| TOC exists but headings are missing | Use TOC to promote matching body lines to segment boundaries |
| TOC entries do not match body | Show low-confidence warning and allow fallback ranges |
| PDF import has broken layout | Use existing structure repair first, then segment with lower confidence |
| Chapter is too large | Split into synthetic child segments such as `Chapter 4 - Part 1` |
| Heading appears inside quote or epigraph | Avoid boundary unless evidence is high |
| Bibliography or references | Mark as bibliography and default to skipped for audiobook |
| Images at chapter boundary | Attach image to nearest owning segment using relations |
| Tables spanning pages | Keep table as atomic block and avoid splitting inside it |
| User reprocesses completed chapter | Create a new artifact bundle for the current session and leave previous saved artifacts untouched |
| Settings changed before processing | Invalidate structure confirmation if settings affect detection |
| Run is stopped mid-segment | Revert `queued` and `processing` segments to `pending`; keep `completed` and `failed` unchanged |
| User changes target language or processing operation mid-session | Keep existing `completed` statuses as historical in-session status; do not auto-invalidate them in Phase 1 |
| Partial translation changes glossary | Update memory and use newer memory version for later segments |
| Same file is analyzed twice and structure differs | Compare `structure_fingerprint`, warn the user, and require confirmation again |

## Logic Flow Diagram

```mermaid
flowchart TD
    A[Upload DOCX/DOC/PDF] --> B[Normalize Uploaded Document]
    B --> C[Extract Paragraph Units, Tables, Images]
    C --> D[Boundary Normalization and Cleanup]
    D --> E[Structure Validation and AI Recognition]
    E --> F[Detect Chapters and Sections]
    F --> G[Build Segment Tree and Diagnostics]
    G --> H[Build Semantic Blocks with Segment Hard Boundaries]
    H --> I[Build Processing Jobs]
    I --> J[Analysis Complete UI]
    J --> K[User Reviews and Confirms Structure]
    J --> T[User Chooses Process Entire Book]
    K --> L[User Selects Segments]
    L --> M[Create Segment-Aware Processing Run]
    M --> N[Filter Jobs by Selected Segment Coverage]
    N --> O[Process Jobs with Global Context and Glossary]
    O --> P[Save Selected Segment Artifacts]
    P --> Q[Update Session Segment Statuses]
    T --> U[Run Existing Full-Book Pipeline]
    U --> V[Write Full-Book Artifacts]
    Q --> R{All Required Segments Complete In Current Session?}
    R -->|No| J
    R -->|Yes| S[Build Final Reassembled DOCX]
```

## Implementation Plan

### Current Delivery Status

- Overall status for the user-facing chapter workflow MVP is approximately 75-80% complete.
- Overall status for the full spec including retry, reassembly, final-book modes, and consistency/context-preservation phases is approximately 45-55% complete.
- `Phase 1` is effectively complete.
- `Phase 2` is mostly complete, with remaining UX/contract polish and consistency work around selection semantics and selector clarity.
- `Milestone B.5` is implemented: the chapter/segment review subsystem now lives in `src/docxaicorrector/ui/structure_review_panel.py`, while `src/docxaicorrector/ui/_app.py` remains the orchestration shell that composes it.
- `Phase 3` is partially complete: structure reproducibility, confirmation invalidation, and a minimal failed-segment retry flow are now in place, but richer manual comparison and deeper job-level retry behavior remain open.
- `Phase 4` and `Phase 5` remain largely ahead.

### Autonomous Execution Plan

This section is the handoff contract for future sessions working on this spec.

Rules for future implementation sessions:

- Prefer milestone-sized deliveries over microscopic slices when the affected code can be changed safely without a large refactor.
- Keep changes minimal and local; do not do a large tree/UI refactor unless the spec is otherwise blocked.
- Do not introduce new event families unless there is a concrete need.
- Do not present retry as a completed Phase 3 capability until it works end-to-end.
- Update this spec only for behavior that is actually implemented.
- Run relevant tests through the WSL debug-side path after each milestone package.
- Treat this spec as the primary handoff artifact between sessions.
- Keep `src/docxaicorrector/ui/_app.py` as an orchestration shell rather than a feature-logic sink. New chapter/segment workflow UI state machines, selector semantics, payload derivation, and other feature-specific UI logic should be extracted into dedicated `ui/` modules with typed input/output contracts once a change goes beyond a small local tweak.
- Prefer adding typed helper contracts (`TypedDict`, `Protocol`, small dataclasses, or narrowly scoped typed helpers) when extending chapter/segment review flows, so future work does not increase dynamic `dict[str, object]` and `object`-typed coupling inside `_app.py`.

Execution order for autonomous work:

1. `Milestone A: Finish Analysis/Review UX`
2. `Milestone B: Close Phase 2 UX/contract polish`
3. `Milestone B.5: Structure Review Panel Decomposition`
4. `Milestone C: Failure/Retry Decision`
5. `Milestone D: Reassembly Foundation`
6. `Milestone E: Final Book Modes`
7. `Milestone F: Context Preservation`

Milestone definitions:

- `Milestone A: Finish Analysis/Review UX`
  - make the confirmed-outline summary more explicit in the analysis panel;
  - make selection summary more section-aware and easier to understand;
  - improve invalidation and disabled-state messaging;
  - add lightweight manual comparison affordances only if they fit the current architecture without a large refactor.
- `Milestone B: Close Phase 2 UX/contract polish`
  - keep parent/child selection semantics consistent across selector state, bulk actions, and selected-processing payloads;
  - improve selector clarity for flat-list section/chapter relationships;
  - avoid a real nested tree UI model unless a blocker appears.
- `Milestone B.5: Structure Review Panel Decomposition`
  - extract the chapter/segment review subsystem from `src/docxaicorrector/ui/_app.py` into a dedicated UI module such as `src/docxaicorrector/ui/structure_review_panel.py` or `src/docxaicorrector/ui/chapter_review_panel.py`;
  - move `_render_analysis_review_panel(...)` and its tightly coupled helpers together rather than splitting them across unrelated modules;
  - move selection expansion helpers, selected-processing payload/effective selection state helpers, and confirmation invalidation/review summary helpers with that panel module;
  - keep `_app.py` as an orchestration shell that composes the feature module rather than owning the chapter-review state machine internally;
  - treat this as the preferred low-risk decomposition boundary before deeper retry or reassembly work, because the chapter-review flow is already a largely self-contained subsystem.
- `Milestone C: Failure/Retry Decision`
  - either implement a real minimal retry flow for failed segments/jobs;
  - or explicitly keep retry as disabled/not-yet-implemented UX without implying completion.
- `Milestone D: Reassembly Foundation`
  - add the reassembly service foundation;
  - first target `selected_only` and `hybrid_document` modes;
  - add artifact coverage manifests.
- `Milestone E: Final Book Modes`
  - complete `selected_with_context` and `final_translated_book` behavior;
  - add session-completeness guards and user-facing gating.
- `Milestone F: Context Preservation`
  - add `DocumentContextProfile`;
  - add glossary extraction and session-scoped consistency support;
  - inject outline/context information into segment processing prompts.

### Phase 1: Segment Detection And Analysis UI

- [x] Add `DocumentSegment`, `SegmentBoundaryEvidence`, and `SegmentDetectionReport` models.
- [x] Add placeholder types `GlossaryTerm` and `SegmentOutlineEntry` for later context-preservation phases.
- [x] Add `document/segments.py` detection logic.
- [x] Reuse TOC title matching helpers from `document/structure_repair.py`.
- [x] Extend `PreparedDocumentData` with segments, diagnostics, `structure_fingerprint`, and `detector_version`.
- [x] Extend `PreparedRunContext` with the same fields and map them through `_build_prepared_run_context(...)`.
- [x] Add analysis result screen with chapter selector.
- [x] Add structure fingerprint, boundary previews, evidence display, and required structure confirmation.
- [x] Add structure manifest export.
- [x] Keep analysis-review state in session flags rather than expanding `ProcessingOutcome`.
- [x] Keep existing full-book processing as the default path.
- [x] Add explicit `Process Entire Book` UI action backed by the legacy/full-book processing path.

### Phase 2: Segment-Aware Processing

- [x] Add segment-to-job mapping.
- [x] Add hard segment boundaries to semantic block generation.
- [x] Update the `build_semantic_blocks(...)` re-export path in `src/docxaicorrector/document/_document.py` so the new `hard_boundary_paragraph_ids` parameter is forwarded correctly from preparation code.
- [x] Add `selected_segment_ids` to processing context.
- [x] Filter jobs by selected segments.
- [x] Add segment-level status updates, preferably by extending existing event payloads in Phase 1.
- [x] Revert `queued` and `processing` segment statuses to `pending` when a run ends with `STOPPED`, while keeping `completed` and `failed` statuses intact.
- [x] Show a minimal segment status summary in the analysis/review UI.
- [x] Add minimal chapter selector filter/search controls for status and title review.
- [x] Lock queued/processing segment rows in the selector while keeping them visible.
- [x] Add minimal `skipped` selector/filter support in the current UI state model.
- [x] Add minimal bulk selector actions for `Select Visible`, `Clear Visible`, and `Select Entire Book`.
- [x] Add minimal row hints for `completed` and `failed` segments in the selector.
- [x] Add a minimal selected-segment status summary near the selection summary.
- [x] Add minimal parent/section-aware selection expansion so selecting a parent includes currently detected descendants in selector state and selected-processing payloads, without a true tree refactor.
- [x] Keep locked `queued`/`processing` descendants excluded from newly expanded parent selections and selected-processing payloads in the current session.
- [x] Derive review-panel selected counts, readiness state, and disabled-state messaging from the same effective selected-processing payload used by the real `start_selected` launch path.
- [x] Show an explicit review-panel note when queued/processing descendants are excluded from the effective selected-processing payload.
- If dedicated `Segment*Event` dataclasses are introduced, update the `ProcessingEvent` type union.

### Phase 3: Structure Reproducibility And Retry

- Keep processing state session scoped.
- [x] Compare repeated same-session detections by `structure_fingerprint` and show an explicit analysis-panel invalidation summary with previous/current fingerprint details when confirmation becomes invalid.
- [x] Allow exporting structure manifests and importing a previously exported `.segments.json` manifest for manual fingerprint comparison in the analysis review panel.
- [x] Show explicit panel-level notice for failed segments with count and actionable retry guidance in the chapter review panel; per-segment status hint now points to `Retry Failed` or manual reselection.
- [x] Add minimal failed-segment retry in the current chapter review flow via `Retry Failed`, which reruns failed segments from the current session through the existing selected-segment processing path; when the current-session block journal clearly identifies failed jobs inside those segments, narrow the retry payload to only those failed jobs. Cross-session or persisted job-level retry-only reuse remains future work.
- [x] Invalidate structure confirmation when detection-affecting settings change.
- [x] Store and compare `confirmed_at_settings_hash` for detection-affecting settings.

### Phase 4: Reassembly And Final Book Generation

- [x] Record `assembly_mode` (`selected_chapters` / `full_document`) and `selected_segment_count` in the result artifact `.meta.json`, threaded from `ProcessingContext.selected_segment_ids` through `finalize_processing_success` to `write_ui_result_artifacts`.
- [x] Add an initial reassembly service that centralizes `assembly_mode` / `output_mode` planning for current full-document and selected-only runs, instead of keeping that branching inline in `late_phases.py`.
- [x] Thread explicit `output_mode` through the current UI, worker, API, and processing contracts for the currently supported modes `selected_only` and `legacy_full_document`, instead of deriving it only from `selected_segment_ids` during finalization.
- Support `selected_only`, `selected_with_context`, `hybrid_document`, and `final_translated_book` output modes consistently across UI, API, and processing contracts.
- [x] Preserve explicit `selected_with_context` through the current processing/reassembly contract for selected-segment runs, instead of collapsing every selected run back to `selected_only` during finalization.
- [x] Implement a true `hybrid_document` assembly path for full-document runs: read persisted segment records from `.run/segment_results/`, merge them with current-run translated segments, fall back to source-backed segment markdown for missing segments, and carry segment provenance into the result manifest.
- [x] Implement a real `selected_with_context` assembly path for selected runs: expand included segments with leading structural context such as front matter or TOC before the first selected segment, keep selected segments translated from the current run, and use source-backed fallback for the prepended context while recording per-segment provenance in the manifest.
- [x] Implement a dedicated `final_translated_book` assembly path for full-document runs: assemble the final artifact only from translated segment outputs of the current run, enforce the completion precondition at reassemble time, and fail the run if any required full-document segment would otherwise fall back to source or remain missing.
- [x] Write segment-aware result artifact manifests (`.result.manifest.json`) for current runs, including included segment ids and per-segment job counts. Current Phase 4 foundation deliberately omits segment titles unless a canonical segment-title source is available in the processing contract.
- [x] Gate the current UI full-book launch so it requests `final_translated_book` only when all required non-skipped segments are complete in the current session; otherwise it stays on `legacy_full_document`.
- [x] Persist a per-segment translated result registry derived from final assembly entries, keyed by `prepared_source_key` and `structure_fingerprint`, and save it under `.run/segment_results/` as the real foundation for future `hybrid_document` reassembly.

Current contract note for the Phase 4 foundation:

- full-document runs currently use the temporary manifest `output_mode` placeholder `legacy_full_document` by default, but the current UI now upgrades that request to `final_translated_book` when all required non-skipped segments are already completed in the session; the dedicated `final_translated_book` reassembly path then enforces that every included segment has translated output and rejects the run if any segment would fall back to source.
- selected-segment `selected_with_context` runs now prepend leading source-backed structural context such as front matter or TOC before the first selected segment and keep the selected segment output translated from the current run; the chapter review panel now exposes this path directly as a `Selected + Context` action alongside `Process Selected`, with explicit `include_front_matter` and `include_toc` toggles.
- full-document `hybrid_document` runs now assemble a mixed artifact from current translated segments, persisted translated registry records, and source-backed fallback segments in original segment order; the manifest records per-segment provenance as `translated` or `source`.

### Phase 5: Translation Memory And Consistency

- [x] Add document context profile.
- [x] Extract glossary candidates.
- [x] Keep translation memory scoped to the current analysis/session in the first implementation.
- [x] Inject glossary and segment summaries into prompts.
- [x] Add UI for terminology review in a later iteration if needed.

Current contract note for the initial Phase 5 slice:

- preparation now builds a session-scoped `DocumentContextProfile` from detected segment outline entries and glossary hits extracted from the current source text;
- `PreparedDocumentData` and `PreparedRunContext` now retain that profile for the active analysis/session;
- translate-mode prompt loading now appends the rendered document context block to the existing `translation_domain_instructions`, so glossary candidates and structural segment summaries reach the system prompt without introducing persisted cross-session memory yet.
- the chapter review UI now exposes a read-only terminology review expander for the current session glossary candidates, so the user can inspect the extracted preferred term mappings before running or rerunning translation.

## Recommended Decision

Use chapters and sections as orchestration and UX units. Keep semantic blocks and jobs as LLM execution units.

This minimizes risk because the existing pipeline already knows how to chunk, prompt, validate paragraph markers, preserve paragraph properties, rebuild DOCX, handle images, and persist UI artifacts. The new segment layer should decide what to process. The existing job layer should continue deciding how to process it.
