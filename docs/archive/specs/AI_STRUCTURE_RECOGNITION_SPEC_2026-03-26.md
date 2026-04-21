# AI Structure Recognition Spec

Date: 2026-03-26
Status: Implemented on 2026-04-17; archived historical design record
Scope: New pre-processing stage — AI-driven document structure classification
Test document: `tests/sources/bernardlietaer-creatingwealthpdffromepub-160516072739 ru.docx`

Archive note:

1. Phase 1 implementation and the scoped Phase 2/3 follow-up work described by this spec landed on 2026-04-17.
2. The remaining heuristic-only heading reduction item was explicitly deferred pending broader multi-document validation and is no longer treated as an active part of this completed workstream.
3. This document is preserved as historical design context rather than an active implementation target.

## 0. Historical Baseline Snapshot

The section below reflects the pre-implementation baseline that this spec was written against. It is retained for historical context only.

Review-validated current state:

1. there is no `structure_recognition.py` module in the repository;
2. there is no `structure_recognition` config surface in `config.py` or `config.toml`;
3. `preparation.py` still runs extraction directly into semantic-block construction with no AI structure-recognition insertion point;
4. paragraph-role enrichment still depends on existing heuristic classification in `document.py`;
5. no dedicated `tests/test_structure_recognition.py` exists yet.

Planning implication:

1. treat this document as a historical design target, not as a current implementation snapshot;
2. do not read the later sections as claims about the present repository state;
3. the sequencing reference below is preserved for design history and points at the archived architecture spec: `docs/archive/specs/ARCHITECTURE_REFACTORING_SPEC_2026-03-25.md`.

## 1. Problem Statement

The current document structure recognition in `document.py` relies on ~200 lines of cascading heuristics (regex patterns, font-size deltas, bold/center detection, text-signal keywords) that attempt to classify paragraph roles (`heading`, `body`, `caption`, `list`, `epigraph`, etc.) from DOCX metadata alone.

**This approach fundamentally cannot work for real-world documents.** Analysis of the full Lietaer book (230 pages, 2321 paragraphs, 1806 non-empty) reveals:

### Evidence from test document

| Style in DOCX | Count | Actual semantic roles mixed inside |
|---------------|-------|------------------------------------|
| Body Text | 1291 | Body, subheadings, epigraphs, attributions, TOC-like, captions |
| Normal | 165 | Chapter markers, part markers, figure captions, author names, epigraphs, TOC entries |
| List Paragraph | 323 | TOC items, actual numbered/bulleted lists, enumerated body content |
| Heading 1-3 | 26 | Real headings (only ~5% of all structural elements) |

**522 short paragraphs** with non-heading styles need semantic classification. Current heuristics detect some via bold/center/font-size, but systematically fail on:

- `"Переосмысление богатства"` — Body Text, no bold, no center → subheading
- `"ЭПИКТЕТ"` — Normal, center, caps → attribution (not heading), but heuristics say "heading"
- `"Деннис Мидоуз"` — Body Text → author name under foreword heading
- `"Системный подход"` — Body Text → subheading
- `"— Билл Маккиббен, автор книги..."` — Normal → review attribution
- `"На момент публикации этой книги"` / `"мы стоим на пороге новой эры"` — Body Text → dedication/epigraph
- `"Содержание"` — Normal, bold → TOC header
- `"Часть I: Местная экономика"` — Normal → part heading (not chapter heading)

**No set of regex rules or formatting heuristics can distinguish these roles** because the classification requires understanding the semantic context: what comes before, what comes after, and what the text means in the document's narrative structure.

### Consequences of misclassification

1. **Wrong chunking**: `build_semantic_blocks` groups paragraphs by role. If a subheading is classified as `body`, it may be merged into the middle of a body block instead of starting a new semantic unit.
2. **Wrong markdown rendering**: `rendered_text` adds `#` prefixes for headings. Missing headings → flat text → LLM doesn't see document structure → worse editing quality.
3. **Wrong formatting restoration**: `preserve_source_paragraph_properties` maps source→output paragraphs by role. Misclassified roles cause wrong style transfers.
4. **Untestable heuristics**: Each new document brings new style combinations. Fixing one case breaks another. The heuristic code path has no stable specification to test against.

## 2. Goals

1. Add a pre-processing AI structure recognition stage that classifies paragraph roles using semantic context, replacing brittle heuristics with a single LLM call.
2. Scale to documents up to 300+ pages (3000+ paragraphs) without exceeding context windows or creating latency bottlenecks.
3. Integrate with the existing pipeline as an enrichment step between extraction and semantic block building — no changes to downstream processing.
4. Maintain full backward compatibility: when AI recognition is unavailable (API failure, user opt-out), fall back to current heuristics transparently.
5. Make the structure map a cacheable, inspectable artifact that aids debugging and validation.

## 3. Non-Goals

- Replacing the editing LLM pipeline (chunking, generation, formatting transfer).
- Changing the DOCX extraction logic (python-docx parsing, XML property reading, role classification). Three new fields (`style_name`, `is_bold`, `font_size_pt`) are added to `ParagraphUnit` and populated during extraction, but the extraction algorithm and role heuristics are unchanged.
- Adding new role types to the main processing pipeline (epigraph/attribution are mapped to existing `role` values; the finer taxonomy lives only in `structural_role`).
- Expanding output formatting back into broad source-style replay. This feature improves semantic classification only; the existing simplified formatting contract remains reference-DOCX-first with minimal post-formatting.
- Restructuring `document.py` beyond preserving extra metadata on `ParagraphUnit`.
- Full TOC parsing or outline reconstruction (future phase).

## 4. Design

### 4.1. Architecture Overview

```
DOCX file
    │
    ▼
┌─────────────────────────────────────────┐
│  Stage 0: DOCX Extraction (minimal Δ)   │
│  document.py → extract paragraphs       │
│  Output: list[ParagraphUnit] with       │
│    explicit styles + raw heuristics     │
│    + style_name, is_bold, font_size_pt  │
└───────────────────┬─────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────┐
│  Stage 1: AI Structure Recognition      │  ◄── NEW
│  structure_recognition.py               │
│                                         │
│  Input: compact paragraph descriptors   │
│  Output: StructureMap (role + level     │
│          + confidence per paragraph)    │
│                                         │
│  Strategy:                              │
│  - Documents ≤2000 paragraphs: 1 call   │
│  - Documents >2000: windowed calls      │
└───────────────────┬─────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────┐
│  Stage 2: Structure Map Application     │  ◄── NEW
│  Enrich ParagraphUnit.role,             │
│  heading_level, role_confidence,        │
│  heading_source from AI map             │
│                                         │
│  Priority: explicit > ai > heuristic    │
└───────────────────┬─────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────┐
│  Stage 3+: Existing pipeline            │
│  build_semantic_blocks (unchanged)      │
│  build_editing_jobs (unchanged)         │
│  LLM generation (unchanged)            │
│  formatting transfer (unchanged)        │
└─────────────────────────────────────────┘
```

### 4.2. New Module: `structure_recognition.py`

Single-responsibility module with three public functions:

```python
# --- Public API ---

def build_structure_map(
    paragraphs: list[ParagraphUnit],
    *,
    client: OpenAI,
    model: str,
    max_window_paragraphs: int = 1800,
    overlap_paragraphs: int = 50,
    timeout: float = 60.0,
) -> StructureMap:
    """Classify paragraph roles via AI. Main entry point."""

def apply_structure_map(
    paragraphs: list[ParagraphUnit],
    structure_map: StructureMap,
) -> None:
    """Enrich ParagraphUnit fields from AI classification. Mutates in-place."""

def build_paragraph_descriptors(
    paragraphs: list[ParagraphUnit],
) -> list[ParagraphDescriptor]:
    """Build compact metadata from ParagraphUnit fields for AI input.
    Reads style_name, is_bold, font_size_pt, paragraph_alignment
    directly from ParagraphUnit — no raw Paragraph access needed."""
```

### 4.3. Data Structures

```python
@dataclass(frozen=True)
class ParagraphDescriptor:
    """Compact metadata sent to AI for classification."""
    index: int                    # Position in document (0-based)
    text_preview: str             # First 60 chars of paragraph text
    text_length: int              # Full text length (helps AI judge body vs heading)
    style_name: str               # DOCX style name ("Body Text", "Normal", etc.)
    is_bold: bool                 # All visible runs are bold
    is_centered: bool             # Paragraph alignment is center
    is_all_caps: bool             # Text is all uppercase
    font_size_pt: float | None    # Dominant font size in points
    has_numbering: bool           # Has Word numPr (native list item)
    explicit_heading_level: int | None  # Non-null only if DOCX style IS a heading

@dataclass(frozen=True)
class ParagraphClassification:
    """AI-assigned role for one paragraph."""
    index: int
    role: str                     # "heading" | "body" | "caption" | "epigraph" |
                                  # "attribution" | "toc_entry" | "toc_header" |
                                  # "dedication" | "list"
    heading_level: int | None     # 1-6 for headings, None otherwise
    confidence: str               # "high" | "medium" | "low"
    rationale: str | None         # Optional 1-sentence explanation (debug only)

@dataclass
class StructureMap:
    """Complete classification result for a document."""
    classifications: dict[int, ParagraphClassification]  # index → classification
    model_used: str
    total_tokens_used: int
    processing_time_seconds: float
    window_count: int             # How many API calls were made

    def get(self, index: int) -> ParagraphClassification | None:
        return self.classifications.get(index)
```

### 4.4. Windowed Strategy for Large Documents

For documents exceeding the practical per-request limit (~1800 non-empty paragraphs, ~36K tokens compact), the system uses overlapping windows:

```
Document: 2400 paragraphs
max_window = 1800, overlap = 50

Window 1: paragraphs [0 .. 1799]     → AI classifies [0 .. 1799]
Window 2: paragraphs [1750 .. 2399]  → AI classifies [1750 .. 2399]
                       ↑ overlap zone

Merge: for paragraphs in overlap [1750..1799]:
  - if both windows agree → use shared classification
  - if they disagree → prefer the window where paragraph is NOT at boundary
    (window 1 for 1750-1774, window 2 for 1775-1799)
```

**Why overlapping windows work**: The AI needs surrounding context to classify a paragraph. A paragraph at the very end of window 1 has no following context; the same paragraph in the middle of window 2 has full context in both directions. The overlap ensures every paragraph appears with adequate context in at least one window.

**Scaling math for the full book**:

| Metric | Value |
|--------|-------|
| Non-empty paragraphs | 1806 |
| Compact JSON per paragraph | ~20 tokens (index + 60-char preview + metadata) |
| Total input tokens | ~36K |
| Context window gpt-4o-mini | 128K tokens |
| **Fits in 1 window?** | **Yes** |
| Output tokens (1806 classifications) | ~15K |
| Estimated cost (gpt-4o-mini) | ~$0.008 |
| Estimated latency | 8-15 seconds |

For a 500-page document (3000+ paragraphs, ~60K input tokens): 2 windows with 50-paragraph overlap, total cost ~$0.015, latency ~20 seconds (can parallelize).

### 4.5. AI Prompt Design

#### System Prompt (structure recognition)

```
You are a document structure analyst. You receive a list of paragraphs from a book
with metadata (text preview, style, formatting). Your task is to classify each
paragraph's semantic role in the document.

## Classification Rules

Assign each paragraph exactly one role:

- "heading": Section/chapter/subsection title. Usually short, may be bold/centered/
  uppercase, starts a new topic. Assign heading_level 1-6:
  - 1: Book parts ("ЧАСТЬ I", "PART II")
  - 1: Chapter titles ("ГЛАВА 1", "CHAPTER 5")
  - 2: Major sections within a chapter
  - 3: Subsections
  - 4-6: Deeper nesting

- "body": Regular paragraph text. The default for long narrative paragraphs.

- "epigraph": Quotation or motto at the beginning of a chapter/section.
  Usually short, centered, italic, appears right after a heading.

- "attribution": Author/source of an epigraph or review quote.
  Usually follows an epigraph or a review paragraph.
  Often starts with "—" or contains "автор книги", author name in caps.

- "caption": Figure/table caption. Contains "Рисунок", "Рис.", "Таблица",
  "Figure", "Table", "Источник:" or similar prefixes.

- "toc_header": "Содержание" / "Contents" heading for table of contents.

- "toc_entry": Individual line in a table of contents listing.

- "dedication": Short text dedicating the book. Usually before the main content.

- "list": Item in an enumerated or bulleted list within body text.

## Key Disambiguation Rules

- Short centered bold text after a heading → likely "attribution" or "epigraph",
  NOT another heading.
- ALL-CAPS short text after a heading → "attribution" (author name), NOT heading.
- Text starting with "—" after a paragraph → "attribution" for the preceding quote.
- "Часть I/II/III" → heading level 1 (book part).
- "ГЛАВА N" → heading level 1 (mapped as chapter start).
- Subheadings within body (short, bold, introducing a new topic) → heading level 3+.
- TOC entries are recognizable as a continuous sequence of short lines listing
  chapter/section names, usually between "Содержание" and the first real chapter.

## Output Format

Return a JSON array. For EACH input paragraph, return one object:
{"i": <index>, "r": "<role>", "l": <heading_level_or_null>, "c": "<high|medium|low>"}

Omit "l" (heading_level) for non-heading roles. Omit rationale in production.
Return ONLY the JSON array, no commentary.
```

#### User Prompt (per window)

```
Classify each paragraph. Metadata format:
{"i": index, "t": "text preview (first 60 chars)", "len": full_length,
 "s": "DOCX style", "b": bold, "ctr": centered, "caps": all_caps,
 "pt": font_size, "num": has_numbering, "hl": explicit_heading_level_or_null}

Paragraphs:
[
  {"i":0,"t":"СОЗДАНИЕ БЛАГОСОСТОЯНИЯ","len":22,"s":"Title","b":false,"ctr":false,"caps":true,"pt":null,"num":false,"hl":1},
  {"i":2,"t":"РАСТУЩЕЕ  МЕСТНЫХ  ЭКОНОМИКИ С     МЕСТНЫМИ","len":52,"s":"Normal","b":false,"ctr":false,"caps":true,"pt":15.5,"num":false,"hl":null},
  ...
]
```

### 4.6. Integration into Existing Pipeline

**Single insertion point**: `preparation.py :: _prepare_document_for_processing`

```python
def _prepare_document_for_processing(source_name, source_bytes, chunk_size, *, progress_callback=None):
    uploaded_file = build_in_memory_uploaded_file(source_name, source_bytes)

    # Stage 0: Extract (unchanged logic, ParagraphUnit now carries
    # style_name, is_bold, font_size_pt populated during extraction)
    paragraphs, image_assets = extract_document_content_from_docx(uploaded_file)

    # ──── NEW: Stage 1 — AI Structure Recognition ────
    from config import load_app_config, get_client
    app_config = load_app_config()
    if app_config.get("structure_recognition_enabled", False):
        structure_map = build_structure_map(
            paragraphs,
            client=get_client(),
            model=app_config.get("structure_model", "gpt-4o-mini"),
        )
        apply_structure_map(paragraphs, structure_map)
    else:
        structure_map = None
    # ──── End NEW ────

    # Stage 2+: Everything below unchanged
    source_text = build_document_text(paragraphs)
    blocks = build_semantic_blocks(paragraphs, max_chars=chunk_size)
    jobs = build_editing_jobs(blocks, max_chars=chunk_size)

    return PreparedDocumentData(...)
```

**Why this is the right insertion point**:
- After `extract_document_content_from_docx` → paragraphs exist with raw metadata
- Before `build_semantic_blocks` → corrected roles improve chunking quality
- Before `build_document_text` → `rendered_text` uses correct `#` heading prefixes
- No code changes needed in `document_pipeline.py`, `generation.py`, or `processing_service.py`
- `formatting_transfer.py` needs no code changes but its diagnostic output will carry new `structural_role` / `role_confidence` values (see §7)

### 4.7. Role Priority and Application Rules

When `apply_structure_map` enriches `ParagraphUnit` fields:

```python
def apply_structure_map(paragraphs: list[ParagraphUnit], structure_map: StructureMap) -> None:
    for paragraph in paragraphs:
        # Rule 1: Explicit and adjacent classifications are NEVER overridden
        if paragraph.role_confidence == "explicit":
            continue
        if paragraph.role_confidence == "adjacent":
            continue

        classification = structure_map.get(paragraph.source_index)
        if classification is None:
            continue

        # Rule 2: Only apply high/medium confidence AI classifications
        if classification.confidence == "low":
            continue

        # Rule 3: Map AI roles to existing pipeline roles
        ai_role = _map_ai_role_to_pipeline_role(classification.role)
        # "heading" → "heading", "body" → "body", "caption" → "caption",
        # "list" → "list", "epigraph" → "body" (with structural_role="epigraph"),
        # "attribution" → "body" (with structural_role="attribution"),
        # "toc_entry"/"toc_header" → "body" (with structural_role="toc"),
        # "dedication" → "body" (with structural_role="dedication")

        paragraph.role = ai_role
        paragraph.role_confidence = "ai"
        paragraph.heading_source = "ai" if ai_role == "heading" else None

        if classification.heading_level is not None:
            paragraph.heading_level = classification.heading_level
        elif ai_role != "heading":
            paragraph.heading_level = None

        if classification.role in ("epigraph", "attribution", "toc_entry", "toc_header", "dedication"):
            paragraph.structural_role = classification.role
        else:
            paragraph.structural_role = ai_role
```

**Priority cascade**: `explicit` / `adjacent` → `ai` (structure map) → `heuristic` (current code, fallback)

### 4.8. Descriptor Extraction (Compact Input Building)

```python
def build_paragraph_descriptors(
    paragraphs: list[ParagraphUnit],
) -> list[ParagraphDescriptor]:
    descriptors = []
    for paragraph in paragraphs:
        if not paragraph.text.strip():
            continue

        text = paragraph.text.strip()
        descriptors.append(ParagraphDescriptor(
            index=paragraph.source_index,
            text_preview=text[:60],
            text_length=len(text),
            style_name=paragraph.style_name,
            is_bold=paragraph.is_bold,
            is_centered=paragraph.paragraph_alignment == "center",
            is_all_caps=text[:60] == text[:60].upper() and any(c.isalpha() for c in text[:60]),
            font_size_pt=paragraph.font_size_pt,
            has_numbering=paragraph.list_kind is not None,
            explicit_heading_level=paragraph.heading_level if paragraph.heading_source == "explicit" else None,
        ))
    return descriptors
```

**Token budget per paragraph**: ~24 tokens in compact JSON form (validated: avg 94.9 chars / 23.7 tokens per descriptor on the full book):
```json
{"i":164,"t":"Переосмысление богатства","len":24,"s":"Body Text","b":true,"ctr":false,"caps":false,"pt":14.0,"num":false,"hl":null}
```

### 4.9. Caching and Artifact Management

Structure maps are cached in two tiers:

1. **Session cache** (in-memory): keyed by `(source_bytes_hash, model)`. Avoids re-running when a user re-processes the same document. Note: the preparation-level cache (§12.2) is the primary staleness guard for the Phase 1 on/off toggle. Model and confidence changes remain an accepted Phase 1 limitation.

2. **Debug artifact** (file): saved to `.run/structure_maps/{filename}_{hash8}.json` for inspection.

Artifact format:
```json
{
  "version": 1,
  "source_file": "bernardlietaer-creatingwealthpdffromepub-160516072739 ru.docx",
  "source_hash": "a1b2c3d4",
  "model": "gpt-4o-mini",
  "timestamp": "2026-03-26T14:30:00Z",
  "total_paragraphs": 1806,
  "window_count": 1,
  "total_tokens": 51200,
  "processing_seconds": 12.3,
  "classifications": [
    {"i": 0, "r": "heading", "l": 1, "c": "high"},
    {"i": 2, "r": "body", "l": null, "c": "medium"},
    ...
  ]
}
```

### 4.10. Error Handling and Fallback

```python
def build_structure_map(...) -> StructureMap:
    try:
        # ... AI call ...
        return parsed_structure_map
    except (APIError, Timeout, JSONDecodeError, ValidationError) as exc:
        log_event("structure_recognition_failed", error=str(exc))
        # Return empty map → apply_structure_map becomes a no-op
        # → pipeline continues with existing heuristic classifications
        return StructureMap(
            classifications={},
            model_used=model,
            total_tokens_used=0,
            processing_time_seconds=0,
            window_count=0,
        )
```

**Contract**: AI structure recognition is always optional. Pipeline correctness never depends on it. An empty `StructureMap` means "use heuristic classifications as before."

### 4.10.1. Timeout, Cancellation, and Background Worker Behavior

Structure recognition runs on the **critical preparation path** — sequentially within `_prepare_document_for_processing`, which is called from the background preparation worker (`prepare_run_context_for_background`). It is **not parallelized** with other preparation steps.

**Timeout**: Each API window call uses `timeout_seconds` from config (default: 60s). On timeout, the window returns empty classifications for that range. If all windows time out, the result is an empty `StructureMap` → full fallback.

**Network/API failure**: Caught in the `except` block above. Logged, empty map returned, preparation continues without delay.

**Background worker cancellation**: The existing background preparation worker does not support mid-flight cancellation (no cancellation token in `_prepare_document_for_processing`). If the user re-uploads a file or navigates away during structure recognition, the background thread completes (or times out) and its result is discarded by the event-draining logic in `app.py`. This is the same behavior as for any long preparation step today.

**Worst-case latency addition to preparation**: 60s (one window timeout). Typical: 5–15s for a full book on gpt-4o-mini. The progress UI (§10.1) communicates this as a distinct stage so the user knows the system is waiting for AI.

### 4.11. Configuration

New fields in `config.toml` and app config:

```toml
[structure_recognition]
enabled = false                  # Master switch; Phase 1 rollout is opt-in
model = "gpt-4o-mini"            # Model for structure analysis
max_window_paragraphs = 1800     # Paragraphs per API call
overlap_paragraphs = 50          # Overlap between windows
timeout_seconds = 60             # Per-window timeout
min_confidence = "medium"        # Minimum confidence to apply ("high" or "medium")
cache_enabled = true             # Session-level caching
save_debug_artifacts = true      # Save .run/structure_maps/*.json
```

## 5. Scaling Validation: Full Book Analysis

### 5.1. Test Document Profile

| Property | Value |
|----------|-------|
| File | `tests/sources/bernardlietaer-creatingwealthpdffromepub-160516072739 ru.docx` |
| Total paragraphs | 2321 |
| Non-empty paragraphs | 1806 |
| Total characters | 576,000 |
| Estimated pages | ~230 |
| Distinct styles | 7 (Title, Heading 1-3, Body Text, Normal, List Paragraph) |
| Explicit headings | 26 (1.4% of all paragraphs) |
| Ambiguous short paragraphs | 522 (need semantic classification) |
| Images | 0 (text-only epub conversion) |
| Font sizes | 9 distinct values (5.5pt to 23.5pt) |

### 5.2. Window Strategy for This Document

| Metric | Value |
|--------|-------|
| Non-empty paragraphs | 1806 |
| Compact JSON chars | 171,422 |
| Compact input tokens (validated) | ~43K |
| gpt-4o-mini context window | 128K tokens |
| **Fits in single window** | **Yes** (43K < 100K safe limit) |
| Estimated output tokens | ~14.5K |
| Total tokens | ~58K |
| Estimated cost (validated) | ~$0.015 |
| Estimated latency | 10-15 seconds |

Technically the 1806 paragraphs produce ~43K input tokens, well within the 128K context window. However, since 1806 > `max_window_paragraphs` (1800), the windowing algorithm produces 2 windows: Window 1 covers paragraphs [0..1799] (1800 paras) and Window 2 covers [1750..1805] (56 paras, with 50-paragraph overlap). In practice this is nearly equivalent to a single window — the second window is tiny and only exists to maintain the invariant. For documents ≤1800 non-empty paragraphs (~220 pages), a true single window applies.

### 5.3. Expected Classification Improvements

Paragraphs that current heuristics misclassify or miss, that AI will handle correctly:

| Paragraph (index) | Current classification | Expected AI classification | Why heuristics fail |
|----|----|----|-----|
| `"Переосмысление богатства"` (164) | body | heading (level 3) | No bold flag in runs, Body Text style |
| `"Системный подход"` (174) | body | heading (level 3) | Same — short but no formatting signal |
| `"Богатство городов"` (195) | body | heading (level 3) | Same pattern |
| `"ЭПИКТЕТ"` (158) | heading (heuristic) | attribution | Centered + caps + short = false heading |
| `"ДЖОРДЖ МОНБИОТ"` (239) | heading (heuristic) | attribution | Same false positive pattern |
| `"Деннис Мидоуз"` (73) | body | attribution | Author name under foreword |
| `"Содержание"` (48) | body | toc_header | Bold + Normal style — heuristic misses |
| `"Часть I: Местная экономика"` (52) | body | toc_entry | In TOC context, not a heading |
| `"ЧАСТЬ I"` (143) | body | heading (level 1) | Normal style, no bold detected, but IS a real heading |
| `"ЧАСТЬ II"` (633) | body | heading (level 1) | Same |
| `"Что такое богатство?"` (53) | list (List Paragraph) | toc_entry | Style says list, semantically it's TOC |
| `"На момент публикации этой книги"` (43) | body | dedication | Dedication before main content |
| `"— Билл Маккиббен, автор книги..."` (12) | body | attribution | Review attribution |
| `"Естественный капитализм плюс"` (87) | body | heading (level 3) | Foreword subsection title |

### 5.4. Token Budget Breakdown

For the full book (validated against real document):

```
Per paragraph (real average from full book):
  {"i":164,"t":"Переосмысление богатства","len":24,"s":"Body Text","b":false,"ctr":false,"caps":false,"pt":14.0,"num":false,"hl":null}
  ≈ 95 characters ≈ 24 tokens (validated: 171,422 chars / 1806 paragraphs)

System prompt: ~800 tokens
User prompt preamble: ~100 tokens
1806 paragraphs × 24 tokens: ~42,855 tokens
────────────────────────────────
Total input: ~43,755 tokens

Output:
1806 × {"i":164,"r":"body","l":null,"c":"high"} ≈ 8 tokens each
Total output: ~14,448 tokens

Grand total: ~58,203 tokens
gpt-4o-mini pricing: $0.15/1M input + $0.60/1M output
Cost: $0.0066 + $0.0087 = $0.0152
```

### 5.5. Scaling Table

| Document size | Pages | Paragraphs | Windows | Input tokens (validated ratio) | Cost | Latency |
|---------------|-------|------------|---------|-------------|------|---------|
| Single chapter | 5-15 | 50-150 | 1 | 1-4K | $0.001 | 2-4s |
| Several chapters | 15-50 | 150-500 | 1 | 4-12K | $0.003-0.006 | 3-8s |
| Full book (Lietaer) | 230 | 1806 | 2* | 44K | $0.015 | 10-15s |
| Large book | 300 | 2500 | 2 | 60K | $0.025 | 15-20s |
| Very large book | 500 | 4000 | 3 | 96K | $0.040 | 20-30s |

\* 2 windows technically, but window 2 is only 56 paragraphs (overlap tail). Effectively single-pass.

For comparison: the main text editing pipeline for the 230-page book processes ~300 LLM chunks at ~$0.02-0.05 each = **$6-15 total**. Structure recognition adds **<0.2%** to total cost.

## 6. Implementation Plan

### Phase 1: Core Module + Integration (this spec)

**New file**: `structure_recognition.py`

**Changes to existing files**:
- `models.py`: add `ParagraphDescriptor`, `ParagraphClassification`, `StructureMap` dataclasses
- `preparation.py`: add structure recognition call between extraction and block building
- `config.py` / `config.toml`: add `[structure_recognition]` section
- `document.py`: export `_resolve_effective_paragraph_font_size` and `_all_runs_bold` helpers (or move to shared utility)

**No changes to**:
- `document_pipeline.py`
- `generation.py`
- `formatting_transfer.py`
- `processing_service.py`
- System prompt

**New tests**:
- `tests/test_structure_recognition.py`:
  - Descriptor building from mock paragraphs
  - JSON prompt serialization/deserialization
  - Windowing logic (overlap, merge)
  - `apply_structure_map` priority rules (explicit > ai > heuristic)
  - Fallback on empty structure map
  - Integration test against the real Lietaer book (marker: `@pytest.mark.integration`)

### Phase 2: Heuristic Deprecation (future)

After validating Phase 1 on multiple documents:
- Move `_is_probable_heading`, `_has_heading_text_signal`, `_paragraph_has_strong_heading_format`, `_promote_short_standalone_headings` behind a `if not ai_classified:` guard
- Track heuristic vs AI classification divergence in formatting diagnostics
- Gradually reduce heuristic code as AI reliability is confirmed

### Phase 3: Extended Taxonomy Consumers (future)

Phase 1 sets `structural_role` to fine-grained values (`epigraph`, `attribution`, `toc_entry`, etc.), but no current consumer reads these for behavioral decisions. In Phase 1, the practical improvement comes only from AI overriding `role` and `heading_level` — correctly classifying heuristic headings/body and fixing heading levels.

`structural_role` becomes actionable in Phase 3 when consumers learn to use it:
- `build_semantic_blocks`: never split epigraph from its heading; treat toc_entry sequences as one block
- `formatting_transfer`: epigraphs keep italic/center even if LLM changes text
- `rendered_text` / markdown rendering: render epigraphs as blockquotes, suppress toc_entry from editing chunks

Until Phase 3, `structural_role` is informational (diagnostics, UI preview, debug artifacts).

## 7. ParagraphUnit Changes

Minimal additions to `ParagraphUnit` in `models.py`:

```python
@dataclass
class ParagraphUnit:
    # ... existing fields unchanged ...

    # New: extended structural role (finer than role)
    # Values: "body", "heading", "caption", "list", "image", "table",
    #         "epigraph", "attribution", "toc_entry", "toc_header", "dedication"
    structural_role: str = "body"  # ALREADY EXISTS — used for extended roles

    # New: style_name preserved from DOCX for descriptor building
    style_name: str = ""

    # role_confidence already exists: "explicit" | "heuristic" | "adjacent"
    # Extended with: "ai" for AI-classified paragraphs
```

The `role` field maps to the 6 existing pipeline roles (`heading`, `body`, `caption`, `list`, `image`, `table`). The `structural_role` field carries the finer AI taxonomy. The main processing path (`build_semantic_blocks`, `rendered_text`, LLM generation) keys on `role`, not `structural_role`, so the core pipeline behavior is unchanged.

**Diagnostic surface impact**: `formatting_transfer.py` serializes `structural_role` and `role_confidence` into formatting diagnostics JSON (`_build_source_registry_entry`), and `_build_caption_heading_conflicts` reads `role_confidence` values. New values (`"ai"` for `role_confidence`; `"epigraph"`, `"attribution"`, `"toc_entry"` etc. for `structural_role`) will appear in diagnostic artifacts and caption-heading conflict reports. This changes the content of `.run/formatting_diagnostics/*.json` and any test assertions that snapshot these artifacts. No code changes in `formatting_transfer.py` are needed — the serialization is generic — but diagnostic expectations shift.

## 8. Risk Assessment

| Risk | Probability | Impact | Mitigation |
|------|------------|--------|------------|
| AI misclassifies paragraphs | Medium | Medium | Confidence filtering (only apply high/medium). Explicit styles never overridden. Diagnostic logging for review. |
| API unavailable | Low | None | Empty StructureMap → full fallback to heuristics. No pipeline breakage. |
| Latency too high for UX | Low | Low | gpt-4o-mini is fast (10-15s for full book). Progress indicator shows dedicated stage. Runs on critical preparation path (sequential, not parallel). Timeout + empty fallback prevents blocking. |
| Output JSON malformed | Low | None | Schema validation. On parse failure → empty map → fallback. |
| Window boundary misclassification | Low | Low | 50-paragraph overlap. Boundary-aware merge prefers non-edge classifications. |
| Cost concerns | Very Low | Very Low | <$0.02 for a full book. <0.2% of total processing cost. |
| Model quality regression | Low | Medium | Structure model version pinned in config. Easy to test with saved artifacts. |

## 9. Verification Criteria

### Must-pass before merge

1. `build_paragraph_descriptors` produces correct compact JSON for Lietaer chapter 1 (75 paragraphs).
2. `build_structure_map` returns valid `StructureMap` for mock input (unit test, mocked API).
3. `apply_structure_map` correctly applies AI roles with priority cascade.
4. Explicit heading styles are NEVER overridden by AI.
5. Empty `StructureMap` (API failure) results in zero changes to paragraphs.
6. Windowing splits 3000-paragraph input into correct overlapping windows.
7. Window merge resolves overlap conflicts correctly.
8. Full pipeline smoke test: Lietaer chapter 1 processes end-to-end with structure recognition ON.
9. Full pipeline smoke test: same document processes with structure recognition OFF (fallback).
10. Existing test suite passes with zero regressions.
11. Config tests (`test_config.py`) pass with the new `[structure_recognition]` section — both default-value wiring and env-override paths (`test_load_app_config_applies_env_overrides_and_clamps`, `test_load_app_config_exposes_image_validation_defaults` which assert all config keys).
12. `build_prepared_source_key` tests (`test_preparation.py`) updated for the new `structure_recognition_enabled` parameter.
13. New `ParagraphUnit` fields (`style_name`, `is_bold`, `font_size_pt`) populated correctly during extraction — verified on a synthetic DOCX fixture.
14. Existing preparation tests continue to pass with structure recognition disabled by default; cache-key tests cover the new `structure_recognition_enabled` parameter.

### Integration validation (post-merge, manual)

15. Run structure recognition on the full book (`bernardlietaer...ru.docx`), inspect artifact JSON:
    - All "ГЛАВА N" paragraphs classified as heading level 1
    - All "ЧАСТЬ N" paragraphs classified as heading level 1
    - Author names (ЭПИКТЕТ, ДЖОРДЖ МОНБИОТ, etc.) classified as attribution, NOT heading
    - TOC entries (indices 48-70) classified as toc_header / toc_entry
    - Body subheadings (Переосмысление богатства, Системный подход, etc.) classified as heading level 3+
16. Compare semantic blocks built with/without structure recognition — blocks should be more semantically coherent with structure recognition ON.

## 10. UI Integration

Structure recognition runs inside the existing preparation phase. It surfaces in the UI through the same mechanisms that every other preparation substage already uses: `emit_preparation_progress` → `SetProcessingStatusEvent` → `processing_status` session state → `render_live_status(phase="preparing")` polled by `st.fragment(run_every=1)`. No new rendering primitives, no new polling loops, no additional fragments.

### 10.1. Progress Stages (preparation.py)

Current preparation emits these progress stages inside `_prepare_document_for_processing`:

| # | Stage | Progress | When |
|---|-------|----------|------|
| 1 | Разбор DOCX | 0.30 | Before `extract_document_content_from_docx` |
| 2 | Структура извлечена | 0.50 | After extraction, before `build_document_text` |
| 3 | Текст собран | 0.65 | After `build_document_text` |
| 4 | Смысловые блоки | 0.80 | After `build_semantic_blocks` |
| 5 | Задания собраны | 0.92 | After `build_editing_jobs` |

The outer `_prepare_run_context_core` in `application_flow.py` wraps these with:

| Stage | Progress | When |
|-------|----------|------|
| Чтение файла | 0.05 | Before file read |
| Файл прочитан | 0.15 | After file read |
| Документ подготовлен | 1.00 | After full pipeline |

Structure recognition inserts between "Структура извлечена" (extraction done) and "Текст собран" (text assembly). The new substage sequence inside `_prepare_document_for_processing`:

| # | Stage | Progress | When |
|---|-------|----------|------|
| 1 | Разбор DOCX | 0.20 | Before extraction |
| 2 | Структура извлечена | 0.30 | After extraction |
| **3** | **Распознавание структуры…** | **0.35** | **Before AI call** |
| **4** | **Структура распознана** | **0.55** | **After AI call + apply** |
| 5 | Текст собран | 0.60 | After `build_document_text` |
| 6 | Смысловые блоки | 0.75 | After `build_semantic_blocks` |
| 7 | Задания собраны | 0.90 | After `build_editing_jobs` |

Progress values are re-distributed to give the AI call (~2–15 s depending on document size) sufficient visual weight. The biggest single jump is 0.35→0.55 — it corresponds to the network-bound LLM call and visually communicates that the system is actively working.

New `emit_preparation_progress` calls:

```python
# Before structure recognition
emit_preparation_progress(
    progress_callback,
    stage="Распознавание структуры…",
    detail="Анализирую роли абзацев с помощью AI.",
    progress=0.35,
    metrics={
        "paragraph_count": len(paragraphs),
        "image_count": len(image_assets),
    },
)

structure_map = build_structure_map(paragraphs, ...)
apply_structure_map(paragraphs, structure_map)

# After structure recognition
emit_preparation_progress(
    progress_callback,
    stage="Структура распознана",
    detail=f"Классифицировано {structure_map.classified_count} абзацев, "
           f"найдено {structure_map.heading_count} заголовков.",
    progress=0.55,
    metrics={
        "paragraph_count": len(paragraphs),
        "image_count": len(image_assets),
        "ai_classified": structure_map.classified_count,
        "ai_headings": structure_map.heading_count,
    },
)
```

When structure recognition is disabled or falls back (API error, opt-out), the two new stages are still emitted but the detail text reflects the fallback:

```python
# Fallback path
emit_preparation_progress(
    progress_callback,
    stage="Структура: эвристика",
    detail="AI-распознавание отключено. Используются текущие правила.",
    progress=0.55,
    metrics={...},
)
```

This keeps the progress bar monotonically advancing regardless of the code path.

### 10.2. Live Status Panel (render_live_status)

No changes to `render_live_status` logic. The function already reads `stage`, `detail`, `progress`, and arbitrary metrics from `processing_status` and renders them via `_render_status_panel`. The new stages flow through the same mechanism automatically.

The second `meta_lines` line in the `phase="preparing"` branch already shows `Абзацы: {paragraph_count} | Изображения: {image_count} | Символы: {source_chars} | Блоки: {block_count}`. None of these need changes — the metrics accumulate as preparation progresses. `source_chars` appears as 0 until the "Текст собран" step, and `block_count` appears as 0 until "Смысловые блоки" — this matches the existing visual behavior.

Optionally (Phase 2 polish), two new metrics can appear in `meta_lines` when they become non-zero:

```python
ai_classified = int(status.get("ai_classified") or 0)
ai_headings = int(status.get("ai_headings") or 0)
if ai_classified:
    meta_lines.append(f"Распознано AI: {ai_classified} | Заголовков: {ai_headings}")
```

This is additive and gated — the extra line only appears after the "Структура распознана" stage, stays through subsequent stages, and disappears once preparation completes and the panel switches to `render_preparation_summary`.

### 10.3. Preparation Summary (render_preparation_summary)

`_store_preparation_summary` in `app.py` builds the static summary dict from `PreparedRunContext`. Add two new optional fields:

```python
st.session_state.latest_preparation_summary = {
    # ... existing fields ...
    "ai_classified": getattr(prepared_run_context, "ai_classified_count", 0),
    "ai_headings": getattr(prepared_run_context, "ai_heading_count", 0),
}
```

`render_preparation_summary` adds a conditional third `meta_lines` entry:

```python
ai_classified = _to_int(summary.get("ai_classified"), default=0)
ai_headings = _to_int(summary.get("ai_headings"), default=0)
if ai_classified:
    meta_lines.append(f"Распознано AI: {ai_classified} | Заголовков: {ai_headings}")
```

This line appears below the existing "MB | абзацев | изображений | символов | блоков" line, only when structure recognition actually ran. When it didn't (disabled or fallback), the summary looks identical to today.

### 10.4. PreparedRunContext / PreparedDocumentData Extensions

`PreparedDocumentData` (returned from `_prepare_document_for_processing`) carries the structure map artifact. Add:

```python
@dataclass
class PreparedDocumentData:
    # ... existing fields ...
    structure_map: StructureMap | None = None  # None when AI recognition didn't run
```

`PreparedRunContext` (built in `application_flow.py`) exposes summary counters for the UI:

```python
@dataclass
class PreparedRunContext:
    # ... existing fields ...
    ai_classified_count: int = 0
    ai_heading_count: int = 0
```

These are populated from `structure_map.classified_count` and `structure_map.heading_count` in `_build_prepared_run_context`.

### 10.5. Session State (state.py)

No schema changes to `processing_status`. The existing dict-based structure already accepts arbitrary keys — the new `ai_classified` and `ai_headings` metrics flow through the same `metrics` parameter of `emit_preparation_progress` → `set_processing_status(**metrics)`.

`latest_preparation_summary` gains two optional keys (`ai_classified`, `ai_headings`) — both int, default 0. Existing rendering code handles missing keys via `.get()` with defaults.

### 10.6. Phase 2: Structure Preview Expander (future)

After Phase 1 is stable, a dedicated expander shows the recognized document structure tree. This follows the same visual pattern as `render_image_validation_summary` (metrics row in `st.columns` + expander with detail).

```python
def render_structure_preview(structure_map: StructureMap | None, target=None) -> None:
    if not structure_map or not structure_map.classifications:
        return
    sink = _get_sink(target)
    with sink.container():
        cols = sink.columns(4)
        cols[0].metric("Всего абзацев", structure_map.total_count)
        cols[1].metric("Распознано AI", structure_map.classified_count)
        cols[2].metric("Заголовки", structure_map.heading_count)
        cols[3].metric("Уверенность", f"{structure_map.avg_confidence:.0%}")

        with sink.expander("Структура документа", expanded=False):
            # Render heading tree as indented markdown
            for cls in structure_map.classifications:
                if cls.role == "heading":
                    indent = "  " * (cls.heading_level - 1)
                    sink.markdown(f"{indent}{'#' * cls.heading_level} {cls.text_preview}")
```

This expander appears between `render_preparation_summary` and the processing controls, only when `structure_map` is available in session state. It is collapsed by default to avoid visual noise, but gives the user a one-click way to verify the document outline before starting processing.

### 10.7. Visual Behavior Summary

| User action | What they see | When |
|-------------|---------------|------|
| Upload a file | Progress bar advancing 0%→20%→30% during DOCX parsing | Immediate |
| (automatic) | Stage "Распознавание структуры…" + spinner, progress 35% | 0–15 s |
| (automatic) | Stage "Структура распознана" + paragraph/heading counts, progress 55% | After AI response |
| (automatic) | Remaining stages (text, blocks, jobs) advance to 100% | Fast, <1 s |
| Preparation complete | Summary panel with existing stats + optional "Распознано AI: N │ Заголовков: M" line | Static |
| (Phase 2) | Collapsed "Структура документа" expander with heading tree | Static, optional |
| AI disabled/failed | Same progress sequence, "Структура: эвристика" stage, no AI-line in summary | Transparent fallback |

### 10.8. What Does NOT Change in UI

- No new Streamlit fragments, no new polling intervals.
- No additional CSS or `_render_trusted_html` calls.
- No changes to the processing phase (`phase="processing"`) rendering.
- No changes to `render_run_log`, `render_image_validation_summary`, compare panel, or download controls.
- `render_file_uploader_state_styles` and `render_intro_layout_styles` untouched.
- The sidebar settings panel is not modified (structure recognition on/off toggle is deferred to Phase 2 config UI).

## 11. File Inventory

| File | Action | Description |
|------|--------|-------------|
| `structure_recognition.py` | **Create** | Core module: descriptors, AI call, windowing, parsing, application |
| `models.py` | **Modify** | Add `ParagraphDescriptor`, `ParagraphClassification`, `StructureMap`; add `style_name` field to `ParagraphUnit` |
| `preparation.py` | **Modify** | Insert structure recognition between extraction and block building; add two new `emit_preparation_progress` calls; extend `build_prepared_source_key` with `structure_recognition_enabled` flag |
| `document.py` | **Modify** | Make `_resolve_effective_paragraph_font_size` public; preserve `style_name` during extraction |
| `config.py` / `config.toml` | **Modify** | Add `[structure_recognition]` config section |
| `application_flow.py` | **Modify** | Propagate `ai_classified_count` / `ai_heading_count` into `PreparedRunContext` |
| `app.py` | **Modify** | Extend `_store_preparation_summary` with `ai_classified` / `ai_headings` fields |
| `ui.py` | **Modify** | Add conditional AI-classification line to `render_preparation_summary`; (Phase 2) add `render_structure_preview` |
| `state.py` | No schema changes | Existing dict-based `processing_status` accepts new metric keys transparently |
| `tests/test_structure_recognition.py` | **Create** | Unit + integration tests |
| `prompts/structure_recognition_system.txt` | **Create** | System prompt for structure analysis |

No changes to: `document_pipeline.py`, `generation.py`, `formatting_transfer.py` (diagnostic output changes, no code changes), `processing_service.py`, `app_runtime.py`.

Existing test files with minor updates: `tests/test_config.py` (new config section), `tests/test_preparation.py` (cache key signature). See §9 for details.

## 12. Open Questions — Resolved

### 12.1. Where do descriptor inputs live?

**Decision: extend `ParagraphUnit` with three new fields; extract from DOCX during `_build_paragraph_unit`.**

The AI structure recognition stage needs compact descriptors with: `text`, `style_name`, `is_bold`, `is_centered`, `font_size_pt`, `char_count`, `source_index`. Current state of these inputs on `ParagraphUnit`:

| Field | Already on ParagraphUnit | Currently computed in |
|-------|--------------------------|----------------------|
| `text` | Yes | — |
| `style_name` | **No** | `_build_paragraph_unit` local variable |
| `is_bold` | **No** | `_paragraph_has_strong_heading_format` (transient) |
| `is_centered` | Indirectly (`paragraph_alignment`) | `_resolve_paragraph_alignment` |
| `font_size_pt` | **No** | `_resolve_effective_paragraph_font_size` (transient, operates on raw `Paragraph` object) |
| `char_count` | Computable from `text` | — |
| `source_index` | Yes | — |

Three fields are missing: `style_name`, `is_bold`, `font_size_pt`. Two options were considered:

**Option A: New return contract from extraction.** `extract_document_content_from_docx` returns a third element — a list of raw descriptor dicts alongside `ParagraphUnit` list. Pros: no ParagraphUnit pollution. Cons: parallel lists are fragile, extraction must re-iterate raw paragraphs, and the data diverges unless kept in sync manually.

**Option B: Extend ParagraphUnit.** Add `style_name: str = ""`, `is_bold: bool = False`, `font_size_pt: float | None = None` directly on the dataclass. Populate in `_build_paragraph_unit` where the raw `Paragraph` object is in scope. Pros: single source of truth, data travels with the paragraph through the whole pipeline, useful for formatting diagnostics even without AI recognition. Cons: 3 new fields on a central dataclass.

**Chosen: Option B.** The fields are small, have sensible defaults, and serve purposes beyond structure recognition (formatting debugging, future heuristic improvements). `is_centered` is already derivable from the existing `paragraph_alignment` field — no additional field needed.

New fields on `ParagraphUnit`:

```python
@dataclass
class ParagraphUnit:
    # ... existing 18 fields ...
    style_name: str = ""           # DOCX style name, e.g. "Body Text", "Heading 1"
    is_bold: bool = False          # True when ≥50% of visible chars are bold
    font_size_pt: float | None = None  # Effective font size in points, None if unresolvable
```

Populated in `_build_paragraph_unit`:

```python
style_name = paragraph.style.name if paragraph.style and paragraph.style.name else ""
is_bold = _paragraph_has_strong_heading_format(paragraph)  # already called, reuse result
font_size_pt = _resolve_effective_paragraph_font_size(paragraph)
```

`build_paragraph_descriptors` in `structure_recognition.py` reads directly from `ParagraphUnit` fields — no parallel data structures, no re-parsing.

### 12.2. What enters the preparation cache key?

**Decision: add `structure_recognition_enabled` flag to `prepared_source_key`. This is required in Phase 1.**

Current cache key: `f"{uploaded_file_token}:{chunk_size}"` — computed in `build_prepared_source_key`. The `uploaded_file_token` is a content-based hash of the file bytes.

The structure recognition step runs inside `_prepare_document_for_processing`, whose return value (`PreparedDocumentData`) is cached. The cached `paragraphs` carry the AI-enriched `role`, `heading_level`, `heading_source`, `role_confidence`, `structural_role` fields. This means if a user toggles structure recognition on/off and re-processes the same file, the cache would return paragraphs with the wrong classification unless the key discriminates the flag.

**New cache key format:**

```python
def build_prepared_source_key(
    uploaded_file_token: str,
    chunk_size: int,
    *,
    structure_recognition_enabled: bool = False,
) -> str:
    sr_suffix = ":sr=1" if structure_recognition_enabled else ""
    return f"{uploaded_file_token}:{chunk_size}{sr_suffix}"
```

Adding the flag is cheap (one bool) and prevents the stale-result scenario entirely. The existing `PREPARATION_CACHE_LIMIT = 2` means at most 2 entries coexist — a toggle simply misses the cache and re-runs preparation, which is the correct behavior.

Model name, `min_confidence`, and other config details are **not** included in the key in Phase 1. These change much less frequently than the on/off toggle, and addressing them would require a full config-hash approach that can be deferred to Phase 2. If model/confidence tuning becomes interactive, extend the key at that point.

**PreparedDocumentData extension**: add `structure_map: StructureMap | None = None` for diagnostics/UI. Cached automatically alongside paragraphs.

### 12.3. Can AI downgrade heuristic headings to body/attribution?

**Decision: yes. AI can override heuristic classifications, but explicit classifications and adjacent captions remain frozen.**

The priority cascade is:

| `heading_source` / `role_confidence` | AI can override? | Rationale |
|--------------------------------------|-------------------|-----------|
| `"explicit"` (Heading 1-6 style, Title, Subtitle, outline level) | **No** | The author explicitly marked this as a heading in Word. The structure is unambiguous. |
| `"heuristic"` (bold+centered+short → heading by format guess) | **Yes** | This is exactly where heuristics fail most. Bold centered text can be an epigraph attribution ("ЭПИКТЕТ"), a dedication, a TOC header — not a heading. The AI sees context and can correctly reclassify. |
| `"adjacent"` (caption reclassified from context) | **No** | Adjacent captions are structural (image/table proximity) and not semantic. AI should not interfere with asset-related classification. |
| Body/list/caption with `role_confidence="heuristic"` | **Yes** | AI can upgrade body to heading, or reclassify body as epigraph/attribution via `structural_role`. |
| Body/list/caption with `role_confidence="explicit"` | **No** | Explicit caption style, explicit list style — these are author-intended. |

Implementation in `apply_structure_map`:

```python
def apply_structure_map(paragraphs: list[ParagraphUnit], structure_map: StructureMap) -> None:
    for paragraph in paragraphs:
        classification = structure_map.get(paragraph.source_index)
        if classification is None:
            continue
        # Never override explicit or adjacent classifications
        if paragraph.role_confidence == "explicit":
            continue
        if paragraph.role_confidence == "adjacent":
            continue
        ai_role = _map_ai_role_to_pipeline_role(classification.role)
        # AI override: both upgrades and downgrades allowed
        paragraph.role = ai_role
        paragraph.heading_level = classification.heading_level
        paragraph.heading_source = "ai" if ai_role == "heading" else None
        paragraph.structural_role = classification.role
        paragraph.role_confidence = "ai"
```

This means a paragraph currently classified as `heading` with `heading_source="heuristic"` (e.g. "ЭПИКТЕТ" — bold, centered, caps, detected as heading by format heuristics) **will be reclassified** to `body` with `structural_role="attribution"` if the AI determines it's an attribution. This is the correct behavior — it's the core value proposition of the feature.

The `"ai"` value is added to the `heading_source` and `role_confidence` vocabularies. The downstream pipeline (`build_semantic_blocks`, `rendered_text`, `formatting_transfer`) keys on `role` (not `heading_source`), so a downgrade from heading to body changes chunking and rendering — which is the desired outcome.

### 12.4. Which existing test files need updates?

**Decision: only two existing test files require minor updates; all other test files are unchanged. New tests go in a new file.**

Analysis of the test surface:

**`tests/test_config.py`** (20 tests):
- Tests assert every key in the app config dict. Adding `[structure_recognition]` config section means default-value tests and env-override tests need to cover the new keys.
- **Change needed**: add test functions for `structure_recognition_enabled`, `structure_model`, etc. or extend parametrized assertions. Existing tests are unaffected since new config keys use defaults.

**`tests/test_preparation.py`**:
- `test_build_prepared_source_key_formats_token_and_chunk_size` — the function signature changes (§12.2). This test needs updating for the new `structure_recognition_enabled` parameter.
- Integration-style preparation tests: structure recognition must be mocked/disabled or rely on the Phase 1 default (`enabled=false`). No assertion changes.
- **Change needed**: update cache key test(s).

**`tests/test_document.py`** (60+ tests, primary risk area):
- 20+ tests assert specific `role`, `heading_level`, `heading_source`, `role_confidence` values from `extract_document_content_from_docx`.
- **These tests all verify extraction output BEFORE structure recognition runs.** Structure recognition is a separate stage that runs in `preparation.py`, after extraction. `extract_document_content_from_docx` returns paragraphs with heuristic/explicit classifications — these don't change.
- Adding `style_name`, `is_bold`, `font_size_pt` fields to `ParagraphUnit` uses defaults (`""`, `False`, `None`) — existing tests that construct `ParagraphUnit` without these fields will not break.
- **Change needed**: none (defaults handle it). Optionally add a targeted test that `style_name`/`is_bold`/`font_size_pt` are populated during extraction.

**`tests/test_format_restoration.py`**, **`tests/test_generation.py`**:
- These test downstream processing. They receive `ParagraphUnit` objects with pre-set roles. Adding new fields with defaults doesn't affect them.
- Formatting diagnostics contain `structural_role` and `role_confidence` — but these tests don't snapshot diagnostic JSON content.
- **Change needed**: none.

**`tests/test_document_pipeline.py`**, **`tests/test_processing_service.py`**:
- End-to-end pipeline tests. Structure recognition will be OFF by default in config. No breakage.
- **Change needed**: none.

**`tests/test_real_document_pipeline_validation.py`**, **`tests/test_real_document_quality_gate.py`**:
- Integration tests against real documents. Threshold-based, not exact-match. May produce different (plausibly better) scores when structure recognition is enabled. Threshold adjustments are done in validation profiles, not in test code.
- **Change needed**: none.

**Summary**:

| Test file | Impact | Change needed |
|-----------|--------|---------------|
| `tests/test_config.py` | New config keys need coverage | **Minor: add tests for `[structure_recognition]` section** |
| `tests/test_preparation.py` | Cache key signature changes | **Minor: update cache key test** |
| All `tests/test_document.py` | None — tests verify pre-AI extraction | **No changes** |
| All `tests/test_format_restoration.py` | None — downstream, receives pre-set ParagraphUnits | **No changes** |
| All `tests/test_generation.py` | None — downstream | **No changes** |
| `tests/test_real_document_*.py` | May improve — threshold-based | **No changes** |
| **`tests/test_structure_recognition.py`** | **New file** | **Created in Phase 1** |

If for any reason a real-document integration test produces a different (better or worse) acceptance score after Phase 1, the threshold can be adjusted in the validation profile — but the test file itself is not modified.
