# Feature Specification: Decompose validation/structural.py (behaviour-preserving)

Date: 2026-07-16
Status: **IMPLEMENTED (2026-07-16).** Pure structural refactor of the ~3110-line
`validation/structural.py`: relocate ~1900 lines of pure leaf clusters into focused `validation/structural_*.py`
modules, leaving a ~1100-line orchestration/processing-service/IO core. No behaviour change.
Owner surface: `validation/structural.py`, new `validation/structural_*.py`, and characterization goldens.

Verification: tests/test_structural_validation_characterization.py holds the Cluster-E / orchestrator / prep-snapshot / TOC-gate goldens byte-identical after each extraction; tests/test_real_document_validation_corpus.py (the orchestrator + monkeypatch net) and tests/test_structure_validation.py green.
Changelog: 2026-07-16 — implemented; status + Non-goals/Anti-regression added to meet the constitution spec-format contract.

## Problem + favourable facts (verified)

Six cleanly-separable pure leaf clusters wrap a cohesive orchestration core. Verified: **no module-level mutable
state / caches / singletons**; the module **never constructs/calls an SDK client** (get_client* are only passed as
callables into `clone_processing_service`; the generation callable is a passthrough) — characterization runs offline.

**Monkeypatch surface (verified exhaustively, multi-line):** all 15 patch sites are in
`tests/test_real_document_validation_corpus.py` (`clone_processing_service`, `get_client*`, `resolve_model_selector`,
`run_structural_passthrough_validation`, `PROJECT_ROOT`, `extract_document_content_with_normalization_reports`,
`load_app_config`, `resolve_runtime_resolution`, `apply_runtime_resolution_to_app_config`,
`build_validation_runtime_config`, `build_semantic_blocks`, `_build_validation_processing_service`). **Every one is
SITUATION 1 (re-export, no repoint) PROVIDED the orchestration core stays resident** — critically
`build_preparation_diagnostic_snapshot` (caller of patched `build_semantic_blocks`) and
`_build_preparation_diagnostic_defaults` (reader of patched `PROJECT_ROOT`) MUST NOT move. The corpus test drives the
orchestrator with everything stubbed and is the primary safety net — it fails immediately on any missed situation-2.

## Scope — staged (re-export only; keep the orchestration/processing-service/IO/CLI core resident)

**Step 0 (prep) — characterization goldens.** Highest-priority: Cluster E (unit-alignment, ~730 lines, untested in
isolation) — snapshot `_derive_unit_aware_unmapped_fields` + the trace from `_emit_target_alignment_trace_artifact`.
Also: an orchestrator golden reusing the corpus stub harness (snapshot `result["metrics"|"checks"|
"preparation_diagnostic_snapshot"]`), a `build_preparation_diagnostic_snapshot` golden (semantic-blocks stubbed), and
Cluster D `_derive_toc_body_concat_gate_fields`. Offline, deterministic JSON goldens. Commit — safety net.

**Extractions (each: move verbatim to `validation/structural_<name>.py`, `from .structural_<name> import (...) # noqa: F401`
re-export in structural.py, bodies byte-identical, leaf modules never import structural at top):**
- **Step 0m** — `structural_metrics_common.py`: `_as_int`, `_as_float` (consumed widely; hoist first to prevent cycles).
- **Step 1** — `structural_event_log.py` (Cluster N): the 7 `_extract_event_context*` extractors.
- **Step 2** — `structural_text_metrics.py` (Cluster M): similarity/drift/markdown detectors + `_relation_count`.
- **Step 3** — `structural_toc_signals.py` (Cluster D): topology/document-map detectors incl. `has_toc_body_concat_structure`,
  `_derive_toc_body_concat_gate_fields`, `_projection_has_units_or_operations` (re-export covers quality_gate's
  deferred imports of `_build_output_artifacts`/`_derive_toc_body_concat_gate_fields`).
- **Step 4** — `structural_unit_alignment.py` (Cluster E, biggest): the unit-accounting/target-alignment block incl.
  `_derive_unit_aware_unmapped_fields`, `_emit_target_alignment_trace_artifact` (imports `_projection_has_units_or_operations`
  from Step 3).
- **Step 5** — `structural_checks.py` (Clusters B+K + `_apply_metric_snapshot_fields`): metric/check builders incl.
  `_build_structural_checks`, `_build_markdown_quality_metrics` (test reads these as module attrs -> re-export = situation 1).
- **Step 6** — `structural_prep_snapshot_helpers.py` (pure subset of the snapshot appliers) incl. the externally-imported
  `_apply_prepared_snapshot_fields`, `_apply_prepared_metric_fields`, `_normalize_snapshot_or_metric_statuses`.
  **KEEP RESIDENT:** `build_preparation_diagnostic_snapshot`, `_build_preparation_diagnostic_defaults` (situation-1 anchors).

**Do NOT split (resident core):** Cluster J processing-service factory (`_build_validation_processing_service` — anchors
the get_client*/clone patches), runtime emitters (O), orchestration entry points (H:
`run_structural_passthrough_validation` etc.), quality-report IO (C, reads PROJECT_ROOT), CLI (P), adapters (Q).

## Test plan (every step)

`tests/test_real_document_validation_corpus.py` (the orchestrator + monkeypatch safety net — mandatory each step),
`tests/test_structure_validation.py`, `tests/test_real_document_pipeline_validation.py` (run_lietaer imports),
`tests/test_root_shim_identity_aliases.py`, `tests/test_script_contract_static.py`, and the new characterization
goldens — all green, no golden diff. Import smoke: `pipeline/quality_gate` + the benchmark/lietaer importers resolve;
both entry orders no cycle.

## Out of scope

- Behaviour changes; splitting the resident orchestration core; moving the two situation-1-anchor functions.
- output_validation.py — spec 035.

## Non-goals

(See also `## Out of scope` above.)

- No behaviour change; the resident orchestration/processing-service/IO/CLI core is NOT split; the two situation-1-anchor functions (`build_preparation_diagnostic_snapshot`, `_build_preparation_diagnostic_defaults`) are NOT moved.
- output_validation.py is out of scope — spec 035.

## Anti-regression

- The characterization goldens (Cluster E unit-alignment `_derive_unit_aware_unmapped_fields` + trace, the orchestrator `metrics/checks/preparation_diagnostic_snapshot`, the `build_preparation_diagnostic_snapshot` golden, and Cluster D TOC-body-concat gate fields) stay byte-identical after every extraction — tests/test_structural_validation_characterization.py.
- All 15 monkeypatch sites remain situation-1 (re-export, no repoint) because the orchestration core stays resident — tests/test_real_document_validation_corpus.py is the primary net (fails immediately on any missed situation-2) + tests/test_structure_validation.py + tests/test_script_contract_static.py.

## SaaS rationale

Neutral; a cohesive validation layer (pure detectors/metrics separated from orchestration/IO) is easier to reuse and test.
