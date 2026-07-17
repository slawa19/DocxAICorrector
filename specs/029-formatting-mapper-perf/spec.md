# Feature Specification: Optimize the formatting-transfer mapper (output-identical)

Date: 2026-07-15
Status: **IMPLEMENTED (2026-07-16).** Performance. Remove the O(S·T·L²) + O(S·T·log T) cost from the formatting
mapper hot path with **provably output-identical** changes, gated by a full-blob golden.
Owner surface: `generation/formatting_transfer.py` (`_map_source_target_paragraphs` and its passes), new
characterization/golden test, new offline profiling harness.
Note: `build/lib/.../formatting_transfer.py` is a stale build artifact — edit only `src/`.

Verification: tests/test_formatting_mapper_golden.py is the gate — the full-blob mapper golden (mapping_pairs + complete diagnostics) is byte-identical after every lever; tests/test_format_restoration.py (99) stays green.
Changelog: 2026-07-16 — implemented; status + Non-goals/Anti-regression added to meet the constitution spec-format contract.

## Problem (verified against HEAD d27c137 + research)

`_map_source_target_paragraphs` (`formatting_transfer.py:2144`) runs ~15 passes; each iterates all sources, and
six passes do `for target_index in sorted(available_target_indexes)` — **re-sorting the target set on every source
iteration**. Two passes scan ALL available targets with no proximity window and run `SequenceMatcher.ratio()`
(O(L²)) per candidate: pass 11 `_try_register_unique_registry_text_floor_mapping` (`:1441`) and pass 13 global
similarity (`:2464`, via `_mapping_similarity_score` `:1072`). `_normalize_text_for_mapping`/`_token_set` are
recomputed per comparison. Net ≈ **O(S·T·L²)** for a book (S≈T≈n), matching the review. The path is **100% pure
CPU / LLM-free** (imports only logging/re/difflib/io/typing + python-docx + internal modules) → profilable offline,
no API key.

## Correctness backbone (the equivalence proof to preserve)

Every pass's final decision is either a count test (`len(...)==1`) or a total-order sort on a tuple containing
`target_index`/`-distance` followed by an ambiguity guard that rejects near-ties. **So long as the target scan stays
ascending and the candidate set is unchanged (or only upper-bound-admissibly pruned), output is provably identical.**
Invariants to preserve everywhere: ascending scan order; greedy `available_target_indexes.discard` semantics;
unchanged thresholds, tuple sort keys, ambiguity guards, and role bonuses (caption +0.08 / list +0.05 / heading
+0.03, mutually exclusive, cap 1.0).

## Scope (planned) — provably-identical levers only

1. **Golden + profiler first (no production change).** Full-blob characterization test: snapshot the ENTIRE
   `_map_source_target_paragraphs` result — `mapping_pairs` as `[(paragraph_id, target_index)]` PLUS the complete
   `diagnostics` dict (per-source `mapping_strategy`, `unmapped_source_ids`, `unmapped_target_indexes`, strategy
   counts, `accepted_split_targets`, …) — to canonical sorted JSON. Inputs built offline: `paragraphs, _ =
   extract_document_content_from_docx(open(book,'rb'))` for the books under `tests/sources/book/`, an identity target
   Document plus a synthesized `generated_paragraph_registry` with deliberate split/merged/renamed entries to force
   the fuzzy passes (9/10/11) and the global pass (13). Commit goldens; require byte-identical output after every
   lever. Keep `tests/test_format_restoration.py` (99 tests) as the fast inner net.
2. **Lever E — memoize** per-target normalized text / token set / length once per call (and per source-candidate);
   pure-function memoization. Removes a large constant factor.
3. **Lever A — single maintained ascending target list** with O(1) `available_target_indexes` membership skip,
   replacing all `sorted(available_target_indexes)`. Same order, same visited set → identical; drops the `log T`.
4. **Lever B — bisect window slicing** for the windowed passes (3/4/9/10: windows 12/3/32/18): iterate only
   `[anchor−W, anchor+W]` via `bisect` on the ascending list. Out-of-window targets were `continue`d anyway.
5. **Lever C — `real_quick_ratio()`/`quick_ratio()` admissible gate** before `ratio()` in passes 11 & 13.
   These are guaranteed upper bounds on `ratio()`. Pass 13: skip `ratio()` when `real_quick_ratio < 0.82`
   (floor 0.9 − max bonus 0.08). Pass 11: skip only when `real_quick_ratio < 0.92` AND `candidate not in target`
   (preserve the containment-accept branch of `_registry_candidate_mapping_evidence`). Provably identical.

6. **Lever F — per-call role-resolution memoization (added after profiling).** Profiling revealed the DOMINANT cost
   in the offline path is python-docx per-target style/role resolution (`_target_format_role`,
   `_target_has_heading_format`, `_extract_target_heading_level`), recomputed O(S·T) times for the same target across
   source iterations. These are pure functions of the target paragraph, and `target_paragraphs` is not mutated during
   mapping, so resolve each once per `_map_source_target_paragraphs` call keyed by target index (O(T) total) and reuse.
   Provably identical (same paragraph → same role). This is the highest-leverage safe win; E/A/B/C removed the
   sort/ratio cost but could not touch role resolution (it takes an unhashable `Paragraph`, so it is outside the
   string-keyed `lru_cache`). Golden must stay byte-identical.

**Out of scope (this spec):** Lever D (token inverted index for pass 13) — NOT provably admissible (char-level ratio
vs word-level index); revisit separately behind a flag only if A/B/C/E are insufficient. Do NOT window passes 11/13
by proximity, reorder passes, change greedy discard, or alter thresholds/sort keys.

## Test plan

- Golden JSON per book is byte-identical before/after each lever (the gate).
- `tests/test_format_restoration.py` (99) stays green after every lever.
- Offline profiling harness (no API): call `_map_source_target_paragraphs(...)` directly; synthetic sweep
  S=T∈{500,1000,2000,4000} with ~30% perturbed targets (forces residuals into passes 11/13) + a real-doc
  confirmation from the largest fixture; `time.perf_counter` + `cProfile`. Report per-scale wall time before/after;
  require golden unchanged at every scale. Pre-fix must show ~quadratic growth; post-fix materially reduced.
- End-to-end suites unaffected: `test_document_pipeline.py`, `test_document_pipeline_output_validation.py`,
  `test_processing_service.py` green.

## Expected outcome

Sorting factor removed; windowed passes O(S·W); the two unbounded passes reduced to O(S·T·L) worst / ≈O(S·T)
typical (length gate eliminates almost all pairs in O(1)). The O(n²·L²) hot path becomes ≈O(n²) with a small
constant, **output provably identical** (golden-enforced).

## Non-goals

(See also the "**Out of scope (this spec)**" paragraph under Scope above.)

- Lever D (token inverted index for pass 13) is excluded — it is not provably admissible (char-level `ratio()` vs word-level index), so it cannot ride the output-identical guarantee.
- No windowing of passes 11/13 by proximity, no pass reordering, no change to greedy `discard` semantics, thresholds, tuple sort keys, or role bonuses — each would break the equivalence proof this spec is built on.

## Anti-regression

- The full-blob characterization golden (per-book `mapping_pairs` + the ENTIRE `diagnostics` dict) is byte-identical before/after every lever — tests/test_formatting_mapper_golden.py (the gate).
- Ascending target-scan order and greedy `available_target_indexes.discard` semantics are preserved (only upper-bound-admissible pruning via `real_quick_ratio`/`quick_ratio`) — tests/test_format_restoration.py (99) green after every lever.

## SaaS rationale

Faster per-document formatting transfer lowers per-job CPU cost and latency — directly relevant once documents are
processed server-side at scale.
