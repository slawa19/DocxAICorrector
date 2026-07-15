# Feature Specification: Decompose generation/formatting_transfer.py (behaviour-preserving)

Date: 2026-07-16
Status: **PLANNED (Wave 3 / decomposition, module 3 of 5).** Pure structural refactor of the ~3505-line
`generation/formatting_transfer.py` into a mapper module + a restoration module + a thin facade. No behaviour change.
Owner surface: `generation/formatting_transfer.py` (shrinks to ~250-line facade), new `generation/formatting_mapping.py`
+ `generation/formatting_restoration.py`, the relation-phase test, and the log-event/CODEOWNERS contracts.

## Problem + favourable facts (verified)

Pure CPU / fully offline (maps formatting onto already-produced target text; only `core.models` import, no LLM).
The mapper cluster is already golden-covered by `tests/test_formatting_mapper_golden.py` (byte-identical over 4 books).
The review's "mapping / restoration / diagnostics" framing needs one correction (verified): the **diagnostics builders
are NOT a separable cluster** — the mapper calls them inline and their whole output is inside the mapper golden's
snapshot, so they move WITH the mapper. The genuine acyclic seams are:
- `formatting_mapping.py` (leaf): the mapper (`_map_source_target_paragraphs` + passes + `_TargetRoleResolver` +
  `real_quick_ratio` gates + registry/evidence/similarity + ALL diagnostics builders + the shared low-level
  text/role helpers incl. the two `@lru_cache`d `_normalize_text_for_mapping`/`_token_set`). ~2870 lines. Keep the
  mapper internally intact (correctness-critical, spec 029).
- `formatting_restoration.py`: docx-apply (image/caption/list/TOC/alignment/quote/split-heading restoration + pPr/XML
  helpers). Imports mapping ONE-WAY (restoration→mapping; mapping never calls restoration → no cycle).
- `formatting_transfer.py` facade (kept): the public entry points (`restore_source_formatting`,
  `preserve_source_paragraph_properties`, `apply_output_formatting`, `_restore_source_formatting_impl`,
  `_build_output_formatting_diagnostics`), `_write_formatting_diagnostics_artifact` + `FORMATTING_DIAGNOSTICS_DIR`,
  `_collect_target_paragraphs`, and re-export blocks.

## Monkeypatch surface (verified exhaustively)

`tests/test_format_restoration.py` patches 4 formatting_transfer attributes:
- `build_paragraph_relations` (357), `resolve_effective_relation_kinds` (358) — read by `_map_source_target_paragraphs`
  which MOVES → **SITUATION 2: repoint both to `formatting_mapping` in Step 1.**
- `log_event` (2853, via `apply_output_formatting` which STAYS) — situation 1, re-export.
- `FORMATTING_DIAGNOSTICS_DIR` (2912/2939/2968, read by `_write_formatting_diagnostics_artifact` which STAYS) —
  situation 1; the constant + its reader MUST stay in the facade.
(The `document_pipeline.FORMATTING_DIAGNOSTICS_DIR` patches elsewhere target the pipeline module, not this one.)

## Scope — staged

**Step 0** — restoration/facade characterization goldens (no move): a new integration-local golden
`tests/test_formatting_restoration_golden.py` — Golden A: canonicalized `word/document.xml` + `word/numbering.xml`
from `preserve_source_paragraph_properties(...)` over a fixture covering list/TOC/centered-caption/attribution/
image/split-heading/epigraph; Golden B: the written diagnostics-artifact JSON (or the 4 restoration-decision keys +
`caption_heading_conflicts`) with `FORMATTING_DIAGNOSTICS_DIR` -> tmp. `UPDATE_*=1` regen. This gates Step 2 (the
mapper is already gated by its own golden).

**Step 1** — extract the mapper → `generation/formatting_mapping.py` (cluster a + shared helpers). Re-export every
facade-reached name (`_map_source_target_paragraphs`, `_build_unmapped_target_residual_diagnostics`,
`_is_heading_like_source_paragraph`, the shared helpers restoration needs). **SITUATION-2 repoint:** change
test_format_restoration.py:357-358 to patch `formatting_mapping.build_paragraph_relations` /
`.resolve_effective_relation_kinds`. Gate: mapper golden byte-identical.

**Step 2** — extract restoration → `generation/formatting_restoration.py` (cluster b + its CENTER_/quote constants).
Imports mapping one-way + `log_event` from core.logger. Re-export into the facade. The `alignment_restoration_skipped`
`log_event` moves out of formatting_transfer → add `formatting_restoration.py` to `scripts/_list_log_events.py` TARGETS
+ `test_script_contract_static.py` expected_targets, and add a CODEOWNERS line mirroring formatting_transfer. Gate:
Golden A/B + mapper golden byte-identical.

**Step 3 (OPTIONAL, deferred)** — split diagnostics builders into `formatting_diagnostics.py`. NOT recommended: they
bidirectionally couple with the mapper (genuine load-time cycle needing function-local imports) for marginal benefit.

## Test plan (every step)

`tests/test_formatting_mapper_golden.py` (byte-identical — mandatory each step), `tests/test_format_restoration.py`
(99), the new restoration golden, `tests/test_root_shim_identity_aliases.py`, `tests/test_script_contract_static.py`,
`tests/test_document_pipeline.py`. Import smoke: `validation/formatting_replay`, `validation/structural`,
`processing/processing_service` import cleanly; both entry orders no cycle.

## Out of scope

- Behaviour changes; the optional diagnostics split; the mapper's internal structure (spec 029, keep intact).
- structural.py / output_validation.py — specs 034-035.

## SaaS rationale

Neutral; a cohesive mapping/restoration split is easier for a backend/worker to reuse and maintain.
