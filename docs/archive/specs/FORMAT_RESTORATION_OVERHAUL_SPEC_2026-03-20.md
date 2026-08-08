# Format Restoration Overhaul Spec

**Date:** 2026-03-20
**Status:** draft
**Supersedes:** DOCX_FORMATTING_RELIABILITY_REFACTOR_SPEC_2026-03-18 (draft, never implemented)
**Related:** LIETAER_QUALITY_REGRESSIONS_SPEC_2026-03-20

---

## 1. Problem Statement

Real-document validation on `tests/sources/Лиетар глава1.docx` reveals four structural fidelity failures that remain after the recent counter-fix and mapping-hardening work:

1. **Phantom text** — LLM output contains text absent from the source (e.g. "Возможно, вы взяли эту книгу, думая, что она подскажет, как увеличить личное состояние — и…"), leaked from `[CONTEXT BEFORE]` into `[TARGET BLOCK]` output.
2. **Numbered lists lost** — Source paragraphs with Word `<w:numPr>` arrive in the output as plain text without list numbering, even though extraction captures `list_num_xml` / `list_abstract_num_xml` correctly.
3. **Alignment destroyed** — Center-aligned paragraphs (epigraph, author attribution) lose alignment in the final DOCX.
4. **Inconsistent heading detection** — Heuristic heading detector produces random results: "ЭПИКТЕТ" (1 word, centered) → heading, "Что такое богатство?" (centered, bold) → NOT heading (rejected by `?` rule), "Миф (и потенциал) индивидуального богатства" (5 words, bold/centered) → NOT heading (rejected by `word_count <= 4` rule).

These are not isolated bugs; they share a common **architectural root cause**: the two-pass format restoration approach in `formatting_transfer.py`, and overly narrow heading heuristics in `document.py`.

---

## 2. Root Cause Analysis

### 2.1. Two-Pass Format Restoration Conflict

**Current pipeline step:**
```
Pandoc DOCX
  → preserve_source_paragraph_properties()   [Pass 1]
  → normalize_semantic_output_docx()          [Pass 2]
  → reinsert_inline_images()
```

Both passes call `_map_source_target_paragraphs()` independently — creating two separate mapping operations on the same document. The result chain is:

1. Pass 1 (`preserve`) maps source→target, then applies preserved `<w:pPr>` XML (including `<w:jc>`, `<w:numPr>`, `<w:ind>`, `<w:spacing>`) via `_apply_preserved_paragraph_properties()`.
2. Pass 2 (`normalize`) maps source→target again (on the already-modified DOCX bytes), then applies semantic styles via `_normalize_output_paragraph()`.

**The conflict:** `_normalize_output_paragraph` sets `paragraph.style = document.styles["Body Text"]` (or "Heading N", "List Paragraph", etc.) via python-docx. This style assignment can **reset or overwrite** direct-formatting properties written by Pass 1:

- `<w:jc w:val="center">` written in Pass 1 gets replaced when python-docx normalizes the `<w:pPr>` during style assignment.
- `<w:numPr>` from Pass 1 references original source numId values. But the numbering definitions from the source document are NOT present in the Pandoc-generated DOCX. These orphaned numId references silently produce no visible numbering. Pass 2 then tries to clone fresh numbering definitions and write new numId values — but if the paragraph already has a `<w:numPr>` from Pass 1, the state is inconsistent.

**Result:** alignment destroyed, list numbering silently lost.

### 2.2. Heading Heuristic Is Too Narrow

`_is_probable_heading()` in `document.py` requires BOTH strong formatting AND `_has_heading_text_signal()`. The text signal check rejects:

| Text | Rejection reason | Should be heading? |
|------|------------------|--------------------|
| "Что такое богатство?" | `endswith("?")` | **Yes** — it's a section title |
| "Миф (и потенциал) индивидуального богатства" | `word_count > 4` (5 words) | **Yes** — centered + bold |
| "Переосмысление богатства" | 2 words, passes | Yes ✓ |
| "ЭПИКТЕТ" | 1 word, passes | Yes ✓ |

The `_has_heading_text_signal` function was designed to prevent false positives (e.g. a short centered epigraph misclassified as heading), but in practice it rejects legitimate headings that have strong visual formatting.

**Core issue:** for short, formatted text (centered or bold), the formatting signal alone should be sufficient when the text is short and clearly non-body.

### 2.3. LLM Context Leakage

`generate_markdown_block()` sends `[CONTEXT BEFORE]` and `[CONTEXT AFTER]` alongside `[TARGET BLOCK]`. The system prompt forbids including context in the response, but:

1. There is no **programmatic validation** that the returned text doesn't contain fragments from the context.
2. In marker mode, `_strip_and_validate_paragraph_markers()` only validates marker integrity (order, count, non-empty chunks), not text content.
3. The LLM can produce a "connecting phrase" or summary-sentence from context as a literary bridge — complying with marker constraints while still leaking content.

---

## 3. Proposed Changes

### 3.1. Merge Two Formatting Passes Into One

The change operates on three layers:

| Layer | What happens |
|-------|-------------|
| **Implementation** | New unified `restore_source_formatting()` in `formatting_transfer.py` — single mapping pass, single restoration loop, correct ordering (style → pPr → numPr). |
| **API surface** | Old public functions become thin compat wrappers: `preserve_source_paragraph_properties` delegates to `restore_source_formatting`; `normalize_semantic_output_docx` becomes a no-op returning its input unchanged. |
| **Pipeline call site** | `run_document_processing()` still calls both callbacks in the same order — the first now does all the work, the second is a safe no-op. No signature change, no caller change. |

**Why keep the two-callback API:** `run_document_processing()` accepts `preserve_source_paragraph_properties: ParagraphPropertiesPreserver` and `normalize_semantic_output_docx: SemanticDocxNormalizer` as separate parameters (lines 345-346 of `document_pipeline.py`). Changing this signature cascades into `processing_service.py`, every test that calls the pipeline, and the callback type aliases. That refactor is out of scope for this work; the compat wrappers make it unnecessary.

`restore_source_formatting()` performs one mapping pass and one restoration loop:

```
For each mapped (source, target) pair:
  1. Apply semantic style (Heading N / Body Text / List Paragraph / Caption / Normal)
  2. Restore direct-formatting properties from preserved_ppr_xml
     — but EXCLUDE <w:pStyle> and <w:numPr> from XML restoration
       (pStyle was just set by step 1; numPr will be set by step 3)
  3. If source.role == "list" and source has numbering XML:
     → clone numbering definition into target numbering_root
     → write <w:numPr> with cloned numId and source ilvl
```

**Key difference:** step 2 happens AFTER step 1, so alignment/indent/spacing survive the style assignment. And `<w:numPr>` is never written twice — it's only written once in step 3 via the cloning logic.

#### What changes in `formatting_transfer.py`

| Current function | Action |
|------------------|--------|
| `preserve_source_paragraph_properties()` | **Compat wrapper** — delegates to `restore_source_formatting()` |
| `normalize_semantic_output_docx()` | **Compat wrapper** — no-op, returns `docx_bytes` unchanged |
| `_normalize_output_paragraph()` | **Kept**, renamed to `_apply_semantic_style()` — only applies style, no longer the entry point for list numbering |
| `_restore_list_numbering_for_mapped_paragraphs()` | **Kept** — called inline after style + pPr for each pair |
| `_apply_preserved_paragraph_properties()` | **Modified** — excludes `pStyle` and `numPr` from applied XML (these are handled by steps 1 and 3) |
| `_map_source_target_paragraphs()` | **Kept** — called once instead of twice |
| `_write_formatting_diagnostics_artifact()` | **Kept** — called once with unified diagnostics |

#### What changes in `document_pipeline.py`

**Nothing.** The pipeline call site stays exactly as-is — two calls to `_call_docx_restorer_with_optional_registry`, first with `preserve_source_paragraph_properties`, then with `normalize_semantic_output_docx`. The behavioral change is inside the compat wrappers: the first call does the unified restoration work, the second returns bytes unchanged.

#### What changes in `tests/test_document_pipeline.py`

Two existing tests are semantically affected (though their assertions still pass with the unchanged pipeline):

1. **`test_run_document_processing_applies_semantic_output_normalization_before_image_reinsertion`** — asserts `call_order == ["convert", "preserve", "normalize", "reinsert"]`. Assertion remains valid (pipeline still calls both). Add a comment clarifying that `normalize` is now a no-op by design.

2. **`test_run_document_processing_passes_generated_paragraph_registry_into_docx_restoration`** — asserts both `preserve_calls == [expected_registry]` and `normalize_calls == [expected_registry]`. After migration, only `preserve` does real work with the registry; the `normalize` wrapper ignores it. The assertion still passes (pipeline still passes registry to both callbacks). Update with a clarifying comment that the real restoration happens in the first call only.

No functional test changes are required — mocks are caller-supplied and keep working. The updates are purely for accuracy of test documentation.

### 3.2. Strengthen Heading Heuristic

**Replace** the current two-gate requirement (`has_strong_format AND has_text_signal`) with a tiered approach:

```
IF has_strong_format AND word_count <= 8 AND char_count <= 100:
    → heading  (short + formatted = heading regardless of text signal)
    EXCEPT:
      - ends with "." and word_count > 4
      - is_caption_style
ELIF has_strong_format AND has_heading_text_signal:
    → heading  (current logic for longer 9-18 word range)
ELSE:
    → not heading
```

Concrete changes to `_is_probable_heading()` in `document.py`:

1. Remove `stripped_text.endswith(("!", "?", ";"))` as a blanket rejection. Question-mark headings ("Что такое богатство?") are legitimate.
2. Widen the "short enough to be a heading" gate from `word_count <= 4` to `word_count <= 8`.
3. Only reject `.`-ending text when `word_count > 4` (already partially implemented for the > 10 case).
4. Keep the `word_count <= 18` and `char_count <= 140` outer bounds.

**New truth table:**

| Text | Format | Words | Will match? |
|------|--------|-------|-------------|
| "ЭПИКТЕТ" | centered | 1 | ✓ short-format |
| "Что такое богатство?" | centered + bold | 3 | ✓ short-format (? no longer rejected) |
| "Миф (и потенциал) индивидуального богатства" | bold | 5 | ✓ short-format (≤ 8 words) |
| "Переосмысление богатства" | centered | 2 | ✓ short-format |
| *Богатство заключается не в том, чтобы иметь много имущества, а в том, чтобы иметь мало желаний.* | centered + italic | 14 | ✗ > 8 words, no text signal → body (correct: epigraph) |
| "Привлекательность лотерейных билетов с крупными призами..." | none | 8+ | ✗ no format → body |

### 3.3. Context Leakage Guard

Add leakage detection **inside the existing retry loop** in `generate_markdown_block()` (lines 504-528 of `generation.py`). No standalone retry mechanism — the leakage check plugs into the same `for attempt in range(1, max_retries + 1):` loop that already handles marker validation and empty-response errors.

**Detection:** new function `_detect_context_leakage()` in `generation.py`:
```python
def _detect_context_leakage(
    response_text: str,
    target_text: str,
    context_before: str,
    context_after: str,
    *,
    min_word_sequence: int = 6,
) -> str | None:
    """Return the leaked fragment if found, else None."""
```
- Extract all contiguous word sequences of length `min_word_sequence` from `response_text`.
- For each sequence, check if it appears in `context_before` or `context_after` but NOT in `target_text`.
- Return the first matched fragment (for logging), or `None`.

**Integration into retry loop — five behaviors:**

1. **Structured match.** Comparison is word-sequence based (≥ `min_word_sequence` contiguous words), not character trigrams. This avoids false positives from common short phrases.

2. **Boundary trim.** If the leaked fragment is at the beginning or end of the response, trim it before returning. If the fragment is interior, do not trim (too risky to cut mid-text).

3. **Retryable validation failure.** When leakage is detected and not fully trimmed, raise a `ContextLeakageError` (new exception class). The retry predicate `_is_retryable_context_leakage_error()` recognizes it, so the existing loop retries naturally — no separate retry mechanism.

4. **Reinforced prompt on retry.** When retrying after `ContextLeakageError`, inject into the user prompt: `"ВАЖНО: Ваш предыдущий ответ содержал текст из контекста. Используйте ТОЛЬКО текст из [TARGET BLOCK]."` (via a flag on `request_kwargs`, analogous to `_boost_request_output_budget`).

5. **Fail-open on last attempt.** If the last attempt still has leakage: apply boundary trim if possible, log `"context_leakage_persisted"`, and return the (possibly trimmed) response. Never block the pipeline for leakage.

**Scope constraint:** LLM paraphrasing of context is not detectable by word-sequence matching. The guard targets the common case: verbatim copy-paste of a phrase or sentence from context.

### 3.4. Comprehensive Source↔Output Comparison Test

Create `tests/test_format_restoration.py` with:

#### Test 1: `test_unified_restoration_preserves_alignment`
- Source DOCX: heading (centered+bold), body (left), epigraph paragraph (centered+italic), body (left, justified)
- Mock LLM output: same text with minor edits
- Pipeline: extraction → mock generation → Pandoc → restore_source_formatting
- Assert: alignment of each output paragraph matches source alignment

#### Test 2: `test_unified_restoration_preserves_list_numbering`
- Source DOCX: "List Number" style paragraphs with Word numPr
- Mock LLM output: same list text
- Pipeline through restoration
- Assert: output paragraphs have `<w:numPr>` with valid numId; numbering_root contains the cloned definition

#### Test 3: `test_unified_restoration_preserves_heading_styles`
- Source DOCX: paragraphs with Heading 1, Heading 2, heuristic-heading (centered short text), Body Text
- Assert: each output paragraph has the correct semantic style

#### Test 4: `test_heading_heuristic_short_formatted_text`
- Parametrized unit test for `_is_probable_heading` with the examples from §3.2 truth table
- Verifies that "Что такое богатство?", "Миф (и потенциал) индивидуального богатства", "ЭПИКТЕТ" all pass

#### Test 5: `test_context_leakage_detection`
- Unit test for `_detect_context_leakage()` with known context and a response containing a verbatim context fragment
- Assert: leakage is detected

#### Test 6: `test_style_assignment_does_not_destroy_alignment`
- Isolated test: create a paragraph with `<w:jc w:val="center">`, assign a style via `_apply_semantic_style`, then re-apply `<w:jc>` from preserved XML
- Assert: final paragraph has center alignment

---

## 4. What Does NOT Change

1. **`_map_source_target_paragraphs()`** — all mapping strategies stay the same. The recent `paragraph_id_registry_similarity` and `_build_generated_registry_candidates` work is preserved.
2. **`_build_processed_paragraph_registry_entries()`** — marker-aware registry construction in `document_pipeline.py` stays as-is.
3. **`_extract_paragraph_list_metadata()`** — list detection in `document.py` stays as-is. Numbered lists are already correctly identified during extraction.
4. **`_capture_preserved_paragraph_properties()`** — XML capture stays as-is. The full set of `PRESERVED_PARAGRAPH_PROPERTY_NAMES` is still captured; only the application order changes.
5. **System prompt** in `prompts/system_prompt.txt` — no changes.
6. **Image pipeline** — no changes.
7. **Test workflow contract** — no changes to `scripts/test.sh` or `.vscode/tasks.json`.
8. **Startup performance contract** — no changes to early startup path.

---

## 5. Implementation Plan

### Phase 1: Merge Formatting Passes (fixes alignment + list numbering)

**Step 1.1.** Create `restore_source_formatting()` in `formatting_transfer.py`:
- Signature: `def restore_source_formatting(docx_bytes: bytes, paragraphs: list[ParagraphUnit], generated_paragraph_registry: Sequence[Mapping[str, object]] | None = None) -> bytes`
- Internal flow:
  1. Filter out tables from source paragraphs
  2. Load Document, collect target paragraphs
  3. Call `_map_source_target_paragraphs()` once
  4. For each `(source, target)` pair:
     a. `_apply_semantic_style(document, target, source)` — current `_normalize_output_paragraph` logic
     b. `_apply_preserved_paragraph_properties(target, source.preserved_ppr_xml)` with `pStyle` and `numPr` excluded
  5. `_restore_list_numbering_for_mapped_paragraphs(document, mapping_pairs)`
  6. Apply Table Grid style
  7. Write diagnostics artifact
  8. Save and return bytes

**Step 1.2.** Modify `_apply_preserved_paragraph_properties()`:
- Add parameter `exclude_names: set[str] = frozenset()` (default empty for backward compat)
- Skip XML fragments whose root element local name is in `exclude_names`
- Callers inside `restore_source_formatting` pass `exclude_names={"pStyle", "numPr"}`

**Step 1.3.** Rename `_normalize_output_paragraph` → `_apply_semantic_style` (internal, no public API change).

**Step 1.4.** `document_pipeline.py` — **no code change needed**. The pipeline call site stays as-is (two sequential `_call_docx_restorer_with_optional_registry` calls). The first callback (`preserve_source_paragraph_properties`) now performs the unified restoration; the second (`normalize_semantic_output_docx`) is a no-op.

**Step 1.5.** Expose `restore_source_formatting` as the canonical public entry point. Keep `preserve_source_paragraph_properties` and `normalize_semantic_output_docx` as **compat wrappers**:
- `preserve_source_paragraph_properties(docx_bytes, paragraphs, registry)` → calls `restore_source_formatting(docx_bytes, paragraphs, registry)` and returns the result.
- `normalize_semantic_output_docx(docx_bytes, paragraphs, ...)` → returns `docx_bytes` unchanged (no-op).

Both wrappers keep their current signatures. `processing_service.py` imports remain valid. No caller changes required.

**Step 1.6.** Update existing tests:
- `tests/test_document.py`: tests calling `normalize_semantic_output_docx` or `preserve_source_paragraph_properties` continue to work (compat wrappers delegate to unified implementation). No functional changes needed.
- `tests/test_document_pipeline.py`: update comments in `test_run_document_processing_applies_semantic_output_normalization_before_image_reinsertion` and `test_run_document_processing_passes_generated_paragraph_registry_into_docx_restoration` to document that `normalize` is now a no-op by design (see §3.1 "What changes in `tests/test_document_pipeline.py`").
- Add new tests for the unified flow in `tests/test_format_restoration.py` (§3.4).

**Step 1.7.** Diagnostics stage labels: the unified `restore_source_formatting()` emits a single `_write_formatting_diagnostics_artifact("restore", ...)` call instead of separate `"preserve"` + `"normalize"` artifacts. The `test_run_document_processing_surfaces_formatting_diagnostics_artifacts` pipeline test is unaffected — it supplies its own mock callback that creates `"preserve_001.json"`, so no real implementation is called.

### Phase 2: Heading Heuristic (fixes inconsistent detection)

**Step 2.1.** Modify `_is_probable_heading()` in `document.py`:
- Remove `stripped_text.endswith(("!", "?", ";"))` blanket rejection
- Add tiered logic:
  ```python
  if has_strong_format:
      if word_count <= 8 and len(stripped_text) <= 100:
          # Short-format gate: heading unless ends with "." and > 4 words
          if stripped_text.endswith(".") and word_count > 4:
              return False
          return True
      return _has_heading_text_signal(stripped_text)
  return False
  ```

**Step 2.2.** Add parametrized test `test_heading_heuristic_short_formatted_text` in `tests/test_document.py`:
- Cases: "ЭПИКТЕТ" (centered), "Что такое богатство?" (centered+bold), "Миф (и потенциал) индивидуального богатства" (bold, 5 words), a 14-word italic sentence (should NOT match)

### Phase 3: Context Leakage Guard (fixes phantom text)

**Step 3.1.** Add `_detect_context_leakage()` in `generation.py` (signature and algorithm described in §3.3 above).

**Step 3.2.** Add `ContextLeakageError` exception class and `_is_retryable_context_leakage_error()` predicate in `generation.py`.

**Step 3.3.** Integrate into the existing retry loop in `generate_markdown_block()`:
- After `_strip_and_validate_paragraph_markers()` succeeds, call `_detect_context_leakage()`.
- If leakage is boundary-only: trim it and return successfully.
- If leakage is interior: raise `ContextLeakageError`.
- Add `_is_retryable_context_leakage_error()` to the retry predicate chain (alongside `is_retryable_error`, `_is_retryable_empty_generation_error`, `_is_retryable_marker_validation_error`).
- On retry after `ContextLeakageError`: set a flag on `request_kwargs` to inject the reinforced anti-leakage instruction.
- **Fail-open:** after the last attempt, if leakage persists, apply boundary trim if possible, log `"context_leakage_persisted"`, and return. Do not raise.

**Step 3.4.** Add unit test `test_context_leakage_detection` in `tests/test_generation.py`.

### Phase 4: Integration Test

**Step 4.1.** Create `tests/test_format_restoration.py` with Tests 1, 2, 3, and 6 from §3.4 (format-restoration integration tests). Tests 4 and 5 live in their respective module test files (`tests/test_document.py` and `tests/test_generation.py`, created in Phases 2 and 3).

---

## 6. Execution Order and Dependencies

```
Phase 1 (merge passes) ─── no dependencies ────────────────── fixes alignment + lists
Phase 2 (heading heuristic) ─── no dependencies ────────────── fixes heading detection
Phase 3 (context leakage) ─── no dependencies ──────────────── fixes phantom text
Phase 4 (integration test) ─── depends on Phase 1 + 2 ──────── regression protection
```

Phases 1, 2, and 3 are independent and can be implemented in any order (or in parallel, if working on separate files). Phase 4 depends on Phase 1 and Phase 2 being complete.

**Recommended order:** Phase 1 → Phase 2 → Phase 4 → Phase 3.

Rationale: Phase 1 has the highest impact (fixes 2 of 4 problems). Phase 2 is a small change. Phase 4 locks in regression coverage. Phase 3 is best-effort and lower priority.

---

## 7. Verification Criteria

### After Phase 1:
- [ ] `test_unified_restoration_preserves_alignment` passes
- [ ] `test_unified_restoration_preserves_list_numbering` passes
- [ ] `test_style_assignment_does_not_destroy_alignment` passes
- [ ] Existing `test_normalize_semantic_output_docx_*` tests pass (via compat wrappers)
- [ ] Existing `test_preserve_source_paragraph_properties_*` tests pass (via compat wrappers)
- [ ] `test_run_document_processing_applies_semantic_output_normalization_before_image_reinsertion` passes (call order unchanged)
- [ ] `test_run_document_processing_passes_generated_paragraph_registry_into_docx_restoration` passes (both callbacks still receive registry)
- [ ] Full pytest green

### After Phase 2:
- [ ] `test_heading_heuristic_short_formatted_text` passes with all parametrized cases
- [ ] "Что такое богатство?" detected as heading
- [ ] "Миф (и потенциал) индивидуального богатства" detected as heading
- [ ] 14-word italic epigraph NOT detected as heading
- [ ] Full pytest green

### After Phase 3:
- [ ] `test_context_leakage_detection` passes
- [ ] Full pytest green

### After Phase 4:
- [ ] `tests/test_format_restoration.py` all green
- [ ] Full pytest green
- [ ] (Manual) Run Lietaer validation, confirm list numbering present in output DOCX
- [ ] (Manual) Run Lietaer validation, confirm alignment preserved in output DOCX

---

## 8. Risk Assessment

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| Style assignment still clears properties even in unified pass | Low | Step 1.1 applies preserved XML *after* style, so direct formatting wins |
| Heading heuristic false positives (short body text wrongly promoted) | Medium | 8-word/100-char gate + "." rejection keeps epigraphs as body |
| Context leakage guard is too aggressive (rejects valid edits) | Low | 6-word minimum avoids matching common phrasing; fail-open (never blocks pipeline) |
| Compat wrappers break test expectations | Low | Wrappers delegate to same logic; pipeline still calls both; test assertions unchanged |
| `_apply_preserved_paragraph_properties` with exclusions introduces regressions | Low | Unit test verifies alignment survives the sequence |

---

## 9. Files Changed

| File | Phase | Change |
|------|-------|--------|
| `formatting_transfer.py` | 1 | New `restore_source_formatting()`, compat wrappers for old entry points, modified `_apply_preserved_paragraph_properties()`, rename `_normalize_output_paragraph` → `_apply_semantic_style` |
| `document_pipeline.py` | 1 | **No change** — pipeline call site stays as-is (compat wrappers absorb the behavioral shift) |
| `document.py` | 2 | Modified `_is_probable_heading()` |
| `generation.py` | 3 | New `_detect_context_leakage()`, `ContextLeakageError`, `_is_retryable_context_leakage_error()`, integration in `generate_markdown_block()` retry loop |
| `tests/test_format_restoration.py` | 4 | New file — 4 integration/unit tests (Tests 1, 2, 3, 6 from §3.4) |
| `tests/test_document_pipeline.py` | 1 | Comment updates in 2 tests (normalize-is-no-op semantic clarification) |
| `tests/test_document.py` | 2 | New parametrized heading heuristic test |
| `tests/test_generation.py` | 3 | New context leakage test |
