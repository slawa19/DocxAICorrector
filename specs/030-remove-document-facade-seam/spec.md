# Feature Specification: Remove the expired extraction-compatibility seam and the _document facade

Date: 2026-07-15
Status: **IMPLEMENTED (2026-07-16).** Tech-debt removal. Delete the expired monkeypatch seam and the
`document/_document.py` facade, repointing all importers to the specialized `document/*` modules. Behaviour-preserving.
Owner surface: `document/_document.py` (deleted), `document/extraction.py` (gains 2 relocated fns), 7 production
importers + 4 non-src scripts, and the seam-dependent tests.

Verification: tests/test_paragraph_boundary_normalization.py and tests/test_document_extraction.py are green AFTER seam deletion (they exercise the exact behaviour the seam propagated); tests/test_formatting_mapper_golden.py stays byte-identical and no `document._document` importer remains.
Changelog: 2026-07-16 — implemented; status + Non-goals/Anti-regression added to meet the constitution spec-format contract.

## Problem (verified against HEAD + research)

`document/_document.py` is a re-export facade with a compatibility seam whose removal deadline
(`EXTRACTION_COMPATIBILITY_OVERRIDE_DEADLINE = "2026-06-30"`, `:79`) has PASSED. `_sync_extraction_compatibility_overrides`
(`:105-112`) `setattr`s an 18-name override map onto `document/extraction.py`'s globals at the top of each extract
entrypoint (`:278/283/288`). **In production this is a functional no-op** — every synced value is byte-identical to
extraction's own definition. Its only real effect is TEST propagation: a test patching a facade global reaches
extraction via the setattr. The facade also carries dead duplicates (`_validate_docx_archive`,
`_read_uploaded_docx_bytes`, report-dir constants) and unused constants (`PARAGRAPH_MARKER_PATTERN`,
`COMPARE_ALL_VARIANT_LABELS`, `MANUAL_REVIEW_SAFE_LABEL`). Only two symbols are facade-unique: `build_document_text`
(`:292`) and `inspect_placeholder_integrity` (`:296`).

## Scope (staged — order is load-bearing)

**Step 0 — relocate the 2 facade-only functions** into `document/extraction.py` (identical signatures):
`build_document_text` and `inspect_placeholder_integrity` (the latter already needs `IMAGE_PLACEHOLDER_PATTERN`, which
lives in extraction).

**Step 1 — repoint production imports** (7 `src/` files + 4 non-src scripts) to the specialized modules:
- `validation/structural.py:29`, `processing/preparation.py:18`, `validation/formatting_replay.py:13`,
  `processing/application_flow.py:20`, `processing/processing_service.py:14` → `extraction` / `semantic_blocks` /
  `boundaries` per the symbol's real home.
- `generation/formatting_transfer.py:22` → `roles` (patterns + role helpers), `extraction` (`IMAGE_PLACEHOLDER_PATTERN`),
  `relations` (`build_paragraph_relations`, `resolve_effective_relation_kinds`).
- `image/reinsertion.py:22` → `extraction` (`IMAGE_PLACEHOLDER_PATTERN`, `_extract_run_text`), `roles`
  (`_find_child_element`→`find_child_element`, `_xml_local_name`→`xml_local_name`). **The underscore→public rename is
  the one behavioural trap — map to the correct public names.**
- Non-src: `benchmark_projects/{pdf_candidate,translation_quality,structure_recognition}_benchmark/benchmark_runner.py`,
  `tests/artifacts/real_document_pipeline/run_lietaer_validation.py`.

**Step 2 — migrate the seam-dependent tests off the facade** (MUST land with/before Step 3): repoint
`test_document_extraction.py`, `test_paragraph_boundary_normalization.py`, `test_document_structure_blocks.py`,
`test_application_flow.py:311`, and the `build_document_text`/`extract_document_content_from_docx` imports in
`test_format_restoration.py` / `test_formatting_mapper_golden.py` / `test_document_pipeline.py` /
`test_preserve_authored_tables.py` to patch/import the specialized modules directly (identical symbols live there).
**Delete `test_document_extraction.py::test_extraction_compatibility_override_inventory_is_explicit_and_applied`
(`:1159`) — it IS the seam self-test.** `test_application_flow.py:311` tests the facade wrapper; retarget to
`semantic_blocks.build_semantic_blocks` forwarding or delete.

**Step 3 — delete the seam machinery**: `EXTRACTION_COMPATIBILITY_OVERRIDE_DEADLINE`,
`EXTRACTION_COMPATIBILITY_OVERRIDE_TARGETS`, `_build_extraction_compatibility_overrides`,
`_sync_extraction_compatibility_overrides`, and the three call sites.

**Step 4 — delete `document/_document.py` entirely.** After Steps 1-3 it has zero importers and no unique content.
A deprecated re-export shim is NOT kept — it would re-introduce the dual-module-identity problem the seam papered over.

## Test plan

- Sharpest signal: `tests/test_paragraph_boundary_normalization.py` (exercises the exact behaviour the seam propagated)
  and `tests/test_document_extraction.py` — green AFTER Step 3 (they silently pass via the seam until it's gone, so
  verify post-deletion).
- Import smoke: all 7 repointed production modules import cleanly.
- `tests/test_format_restoration.py`, `test_formatting_mapper_golden.py` (golden byte-identical),
  `test_document_pipeline.py`, `test_preserve_authored_tables.py`, `test_document_structure_blocks.py`,
  `test_application_flow.py` green.
- `grep -r "document._document"` returns nothing (src + tests + benchmarks + scripts).
- Full no-LLM suite green.

## Out of scope

- Any change to extraction/roles/relations/semantic_blocks behaviour (byte-identical relocation only).
- Decomposition of the large modules (separate specs).

## Non-goals

(See also `## Out of scope` above.)

- No change to extraction/roles/relations/semantic_blocks behaviour — byte-identical relocation of the two facade-only functions only.
- No decomposition of the large modules — that is specs 031-035.
- No deprecated re-export shim for `document/_document.py` is kept — a shim would re-introduce the dual-module-identity problem the seam papered over.

## Anti-regression

- The behaviour the compat seam silently propagated survives its removal — tests/test_paragraph_boundary_normalization.py + tests/test_document_extraction.py green AFTER Step 3 deletes the seam (NOTE: these pass via the seam until it is gone, so the invariant is only proven post-deletion — this is the non-obvious part of this spec).
- No residual `document._document` importer remains anywhere (src + tests + benchmarks + scripts) and downstream output is unchanged — tests/test_formatting_mapper_golden.py (golden byte-identical) + test_document_pipeline.py + test_document_structure_blocks.py.

## SaaS rationale

Neutral; removes a real, expired tech-debt seam and the dual-module-identity hazard, simplifying the document layer a
future backend imports.
