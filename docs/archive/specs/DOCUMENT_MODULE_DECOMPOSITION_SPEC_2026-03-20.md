# Document Module Decomposition Spec

**Date:** 2026-03-20  
**Status:** completed  
**Trigger:** document.py grew to 2339 lines and mixed three independent responsibility domains — DOCX extraction/classification, formatting transfer/mapping, and image reinsertion — making debugging and maintenance of the formatting pipeline disproportionately difficult after real-run regressions documented in `DOCX_FORMATTING_RELIABILITY_REFACTOR_SPEC_2026-03-18.md`.

---

## 1. Problem Statement

`document.py` accumulated 80+ functions across three logically independent domains:

1. **DOCX extraction and paragraph classification** — parsing source docx, building paragraph units, classifying roles, block assembly, text rendering, validation;
2. **Formatting transfer** — source-to-target paragraph mapping, preserved paragraph property restoration, semantic style normalization, list numbering restoration, formatting diagnostics;
3. **Image reinsertion** — image placeholder replacement in generated DOCX, variant resolution, multi-variant comparison table construction, run-level and paragraph-level replacement strategies.

These domains share a small set of XML utility functions and constants but otherwise have no internal coupling. Mixing them in one file created several maintainability problems:

1. formatting bugs required navigating 2300+ lines of unrelated image and extraction code;
2. changes to image reinsertion could accidentally affect formatting transfer and vice versa;
3. test files needed to monkeypatch functions in `document` even when testing pure formatting or pure image logic;
4. code review of any single domain required loading the entire file.

---

## 2. Previous State (Before Decomposition)

### 2.1. `document.py` — 2339 Lines, 80+ Functions

Single monolithic module containing all three domains. Key exports consumed by other modules:

| Consumer | Imported From `document` |
|---|---|
| `processing_service.py` | `inspect_placeholder_integrity`, `normalize_semantic_output_docx`, `preserve_source_paragraph_properties`, `reinsert_inline_images` |
| `document_pipeline.py` | Protocol-based DI — no direct imports of moved functions |
| `tests/test_document.py` | All public + some private functions from all three domains |
| `tests/test_document_pipeline.py` | `extract_document_content_from_docx` + `__import__("document")` for DI wiring |
| `tests/artifacts/.../run_lietaer_validation.py` | Functions from all three domains |

### 2.2. Shared Infrastructure Inside `document.py`

The following constants and helpers were used across multiple domains:

**Constants:**
- `IMAGE_PLACEHOLDER_PATTERN` — used by extraction, formatting transfer, and image reinsertion
- `HEADING_STYLE_PATTERN` — used by extraction and formatting transfer
- `CAPTION_PREFIX_PATTERN` — used by extraction and formatting transfer
- `COMPARE_ALL_VARIANT_LABELS` — used by extraction and image reinsertion
- `MANUAL_REVIEW_SAFE_LABEL` — used by image reinsertion
- `PRESERVED_PARAGRAPH_PROPERTY_NAMES` — used by extraction and formatting transfer
- `INLINE_HTML_TAG_PATTERN`, `MARKDOWN_LINK_PATTERN` — used by formatting transfer
- `ORDERED_LIST_FORMATS`, `UNORDERED_LIST_FORMATS` — used by extraction only
- `RELATIONSHIP_NAMESPACE` — used by extraction only

**Shared XML Utility Functions:**
- `_xml_local_name(tag)` — used by formatting transfer and image reinsertion
- `_find_child_element(parent, local_name)` — used by all three domains
- `_get_xml_attribute(element, attribute_name)` — used by extraction and formatting transfer
- `_extract_run_text(run_element)` — used by extraction and image reinsertion
- `_is_likely_caption_text(text)` — used by extraction and formatting transfer
- `_detect_explicit_list_kind(text)` — used by extraction and formatting transfer
- `_resolve_paragraph_outline_level(paragraph)` — used by extraction and formatting transfer

---

## 3. Design Decision

### 3.1. Decomposition Boundary

Split by responsibility domain, not by abstraction layer:

| Module | Responsibility |
|---|---|
| `document.py` | DOCX extraction, paragraph classification, block building, shared XML utilities, constants, validation |
| `formatting_transfer.py` | Source-to-target paragraph mapping, preserved property restoration, semantic style normalization, list numbering restoration, formatting diagnostics |
| `image_reinsertion.py` | Image placeholder replacement in generated DOCX, multi-variant comparison tables, variant resolution |

### 3.2. Dependency Direction

```
document.py (shared constants + XML helpers)
    ▲                    ▲
    │                    │
formatting_transfer.py   image_reinsertion.py
```

- `formatting_transfer.py` imports constants and helpers FROM `document.py`
- `image_reinsertion.py` imports constants and helpers FROM `document.py`
- `document.py` does NOT import from either new module
- No circular imports

### 3.3. What Stays In `document.py`

All constants and helper functions that are shared across domains remain in `document.py` as the canonical source. This avoids:
1. duplicating constants across modules;
2. creating a new `document_shared.py` or `document_utils.py` module that would add indirection without reducing complexity;
3. forcing extraction code to import from a module named after a different domain.

---

## 4. New Module: `formatting_transfer.py` (728 Lines)

### 4.1. Module Purpose

Paragraph mapping and DOCX formatting restoration. Handles source-to-target paragraph alignment, preserved property transfer, semantic style normalization, and list numbering restoration.

### 4.2. Imports From `document.py`

```python
from document import (
    HEADING_STYLE_PATTERN,
    IMAGE_PLACEHOLDER_PATTERN,
    INLINE_HTML_TAG_PATTERN,
    MARKDOWN_LINK_PATTERN,
    PRESERVED_PARAGRAPH_PROPERTY_NAMES,
    _detect_explicit_list_kind,
    _find_child_element,
    _get_xml_attribute,
    _is_likely_caption_text,
    _resolve_paragraph_outline_level,
    _xml_local_name,
)
```

### 4.3. Other Imports

```python
from logger import log_event
from models import ParagraphUnit
```

Plus stdlib: `json`, `logging`, `re`, `time`, `difflib.SequenceMatcher`, `io.BytesIO`, `pathlib.Path`, `typing.Mapping`, `typing.Sequence`.  
Plus `python-docx`: `Document`, `WD_ALIGN_PARAGRAPH`, `OxmlElement`, `parse_xml`, `qn`, `Paragraph`.

### 4.4. Module-Level Constants

```python
FORMATTING_DIAGNOSTICS_DIR = Path(".run") / "formatting_diagnostics"
```

(Moved from `document.py` — only used by formatting transfer diagnostics.)

### 4.5. Public Functions

| Function | Signature |
|---|---|
| `preserve_source_paragraph_properties` | `(docx_bytes: bytes, paragraphs: list[ParagraphUnit], generated_paragraph_registry: Sequence[Mapping[str, object]] \| None = None) -> bytes` |
| `normalize_semantic_output_docx` | `(docx_bytes: bytes, paragraphs: list[ParagraphUnit], generated_paragraph_registry: Sequence[Mapping[str, object]] \| None = None) -> bytes` |

### 4.6. Internal Functions (23 Total)

Mapping layer:
- `_map_source_target_paragraphs` — core mapping algorithm (positional, exact-match, similarity)
- `_mapping_similarity_score` — text similarity scoring for paragraph alignment
- `_register_mapping` — bookkeeping for mapping state
- `_collect_target_paragraphs` — extract target paragraphs from DOCX
- `_normalize_text_for_mapping` — text normalization for comparison
- `_build_generated_registry_by_paragraph_id` — registry lookup helper

Formatting application:
- `_normalize_output_paragraph` — apply semantic styles to a single paragraph
- `_apply_preserved_paragraph_properties` — restore preserved XML properties
- `_ensure_paragraph_properties` — ensure `pPr` element exists
- `_style_exists` — check if a named style exists in the document
- `_restore_list_numbering_for_mapped_paragraphs` — restore Word numbering XML
- `_get_target_numbering_root` — access numbering definitions
- `_next_numbering_identifier` — allocate numbering IDs
- `_append_numbering_definition` — create abstractNum/num entries
- `_apply_list_numbering_to_paragraph` — set numPr on target paragraph

Diagnostics:
- `_write_formatting_diagnostics_artifact` — emit JSON diagnostics to `.run/`
- `_paragraph_preview` — truncated text for diagnostics
- `_build_source_registry_entry` — diagnostic registry entry
- `_build_target_registry_entry` — diagnostic registry entry
- `_build_caption_heading_conflicts` — detect caption/heading misclassification
- `_extract_target_heading_level` — heading level from target paragraph

---

## 5. New Module: `image_reinsertion.py` (628 Lines)

### 5.1. Module Purpose

DOCX image reinsertion and variant resolution. Replaces image placeholders in generated DOCX files with actual image bytes, handles multi-variant comparison tables, and resolves final image selection.

### 5.2. Imports From `document.py`

```python
from document import (
    COMPARE_ALL_VARIANT_LABELS,
    IMAGE_PLACEHOLDER_PATTERN,
    MANUAL_REVIEW_SAFE_LABEL,
    _extract_run_text,
    _find_child_element,
    _xml_local_name,
)
```

### 5.3. Other Imports

```python
from models import ImageAsset, get_image_variant_bytes
```

Plus stdlib: `re`, `copy.deepcopy`, `io.BytesIO`, `typing.cast`.  
Plus `python-docx`: `Document`, `OxmlElement`, `qn`, `Emu`, `Table`, `Paragraph`, `Run`.  
Plus `lxml.etree`.

### 5.4. Public Functions

| Function | Signature |
|---|---|
| `resolve_final_image_bytes` | `(asset: ImageAsset) -> bytes` |
| `resolve_image_insertions` | `(asset: ImageAsset) -> list[tuple[str \| None, bytes]]` |
| `reinsert_inline_images` | `(docx_bytes: bytes, image_assets: list[ImageAsset]) -> bytes` |

### 5.5. Internal Functions (28 Total)

Paragraph iteration:
- `_iter_reinsertion_paragraphs` — yields paragraphs from all document story containers
- `_iter_section_story_containers` — yields body, headers, footers
- `_iter_container_paragraphs` — recursive paragraph iteration including nested tables
- `_iter_textbox_paragraphs` — paragraph iteration inside textbox elements

Placeholder replacement strategies:
- `_find_known_placeholders` — detect placeholder patterns in text
- `_replace_run_level_placeholders` — replace when placeholder is in a single run
- `_replace_multi_run_placeholders` — replace when placeholder spans runs
- `_replace_paragraph_placeholders_fallback` — paragraph-level fallback
- `_replace_multi_variant_placeholders_with_tables` — comparison table mode

Element construction:
- `_build_run_replacement_elements` — build replacement run elements
- `_build_insertion_run_elements` — build run elements for image insertion
- `_build_text_run_element` — create text run
- `_build_picture_run_element` — create picture run with image bytes
- `_build_picture_size_kwargs` — compute picture dimensions from asset metadata
- `_build_variant_table_element` — build comparison table for multi-variant mode
- `_configure_variant_table_layout` — set table column widths
- `_set_picture_description` — set alt-text on picture element
- `_copy_run_properties` — copy formatting from template run
- `_replace_xml_element_with_sequence` — replace one XML element with multiple
- `_build_replacement_blocks_from_fragments` — assemble replacement paragraph elements

Utilities:
- `_append_image_insertions_to_paragraph` — append multiple image insertions
- `_clone_paragraph_element` — deep-copy paragraph XML
- `_paragraph_element_has_content` — check for non-empty runs
- `_extract_paragraph_child_text` — extract text from paragraph child elements
- `_clear_paragraph_runs` — remove all runs from a paragraph

---

## 6. Remaining `document.py` (1072 Lines)

### 6.1. Retained Responsibilities

1. DOCX extraction: `extract_document_content_from_docx`, `extract_paragraph_units_from_docx`, `extract_inline_images`
2. Paragraph classification: `classify_paragraph_role`, `_infer_role_confidence`, `_is_probable_heading`, etc.
3. Block building: `build_semantic_blocks`, `build_editing_jobs`, `build_document_text`, `build_marker_wrapped_block_text`
4. Paragraph rendering: `_build_paragraph_text_with_placeholders`, `_render_table_html`, `_render_run_element`, etc.
5. Shared constants: all `*_PATTERN` regexes, `COMPARE_ALL_VARIANT_LABELS`, `PRESERVED_PARAGRAPH_PROPERTY_NAMES`, etc.
6. Shared XML helpers: `_xml_local_name`, `_find_child_element`, `_get_xml_attribute`, `_extract_run_text`, etc.
7. Validation: `validate_docx_source_bytes`, `inspect_placeholder_integrity`

### 6.2. Removed From `document.py`

**Imports removed** (no longer needed after function extraction):
- `deepcopy`, `SequenceMatcher`, `json`, `time`, `Path`, `logging`
- `WD_ALIGN_PARAGRAPH`, `OxmlElement`, `parse_xml`, `qn`, `Emu`, `Run`
- `log_event`, `get_image_variant_bytes`
- `Mapping`, `Sequence`

**Constant removed:**
- `FORMATTING_DIAGNOSTICS_DIR` — moved to `formatting_transfer.py`

---

## 7. Consumer Updates

### 7.1. `processing_service.py`

Before:
```python
from document import (
    inspect_placeholder_integrity,
    normalize_semantic_output_docx,
    preserve_source_paragraph_properties,
    reinsert_inline_images,
)
```

After:
```python
from document import inspect_placeholder_integrity
from formatting_transfer import normalize_semantic_output_docx, preserve_source_paragraph_properties
from image_reinsertion import reinsert_inline_images
```

### 7.2. `document_pipeline.py`

No changes. Uses Protocol-based dependency injection — functions are passed as callables at wiring time by `processing_service.py`, not imported directly.

### 7.3. `tests/test_document.py`

1. Added `import formatting_transfer` and `import image_reinsertion` for monkeypatch targets.
2. Split `from document import (...)` into three `from ... import (...)` blocks.
3. Redirected 5 `monkeypatch.setattr(document, ...)` calls to `formatting_transfer` or `image_reinsertion` as appropriate.

### 7.4. `tests/test_document_pipeline.py`

Changed 3 `__import__("document")` calls in DI wiring to:
- `__import__("formatting_transfer").preserve_source_paragraph_properties`
- `__import__("formatting_transfer").normalize_semantic_output_docx`
- `__import__("image_reinsertion").reinsert_inline_images`

### 7.5. `tests/artifacts/real_document_pipeline/run_lietaer_validation.py`

Import split across the three modules.

---

## 8. What Did NOT Change

1. No behavioral changes — all public function signatures, return types, and semantics are identical.
2. No new abstractions introduced — no base classes, protocols, or abstract interfaces added.
3. `document_pipeline.py` unchanged — Protocol-based DI insulates it from import path changes.
4. No test logic changed — only import paths and monkeypatch target modules updated.
5. Constants and shared helpers remain in `document.py` — no `document_utils.py` or shared module created.
6. No configuration, prompt, or runtime artifact changes.

---

## 9. Dependency Graph (After Decomposition)

```
constants ── models ── document.py
                         ▲    ▲
                         │    │
         formatting_transfer  image_reinsertion
                ▲    ▲              ▲
                │    │              │
      processing_service    processing_service
                │                   │
          document_pipeline (via Protocol DI)
```

No circular dependencies. Both new modules depend only on `document.py` (for shared constants/helpers), `models.py`, and external libraries.

---

## 10. Verification

Full test suite: **396 passed, 4 skipped** (unchanged from before decomposition).

No new tests were added — this is a pure structural refactoring with no behavioral change.

---

## 11. Line Count Summary

| Module | Before | After | Delta |
|---|---|---|---|
| `document.py` | 2339 | 1072 | −1267 |
| `formatting_transfer.py` | — | 728 | +728 |
| `image_reinsertion.py` | — | 628 | +628 |
| **Total** | **2339** | **2428** | **+89** |

The +89 line increase is from module docstrings, import statements, and whitespace in the two new files.
