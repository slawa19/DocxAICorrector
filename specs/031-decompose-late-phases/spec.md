# Feature Specification: Decompose pipeline/late_phases.py (behaviour-preserving)

Date: 2026-07-15
Status: **IMPLEMENTED (2026-07-16).** Pure structural refactor of the 4913-line
mixed-responsibility `pipeline/late_phases.py` into cohesive modules, one cluster per commit, characterization
goldens first. No behaviour change.
Owner surface: `pipeline/late_phases.py` (shrinks to finalize + re-export shim), new `pipeline/*` modules, the
seam-dependent tests, and `scripts/run-reader-cleanup-lineage-rebuild-harness.py` (namespace importer).

Verification: tests/test_late_phases_characterization.py holds the Step-0 goldens byte-identical after every cluster extraction (plus the monkeypatch-contract regression test); tests/test_document_pipeline.py and tests/test_script_contract_static.py stay green.
Changelog: 2026-07-16 — implemented; status + Non-goals/Anti-regression added to meet the constitution spec-format contract. Monkeypatch scope was corrected during implementation — THREE patched module attributes (not two): `collect_recent_formatting_diagnostics_artifacts` (situation-1 re-export) plus the situation-2 constants `QUALITY_REPORTS_DIR` (17 sites) and `READER_CLEANUP_LINEAGE_DIR` (2 sites), whose patch sites were repointed to the new modules.

## Problem

`late_phases.py` co-locates markdown normalization, reader-cleanup DOCX rebuild, reader-cleanup/audiobook LLM
postprocess (via DI), quality-gate decisioning (~1550 lines), quality-report retention I/O, terminal-result emitters,
build-phase glue, and the `finalize_processing_success` orchestrator. Favourable facts (verified): **no module-level
mutable state / singletons / `global`** — every module binding is an immutable constant; and the whole module is
**offline-drivable** — the LLM is reached only through injected `dependencies` callables, never a module-level SDK
client. So it is unusually safe to split.

## Central constraint — the monkeypatch surface (verified, CORRECTS the research)

Tests reach ~40 private symbols as `late_phases.<name>` and monkeypatch THREE module attributes (verified by grep,
not two as first scoped):
- `collect_recent_formatting_diagnostics_artifacts` — 13 sites (Cluster D fn)
- `QUALITY_REPORTS_DIR` — **17 sites** (Cluster E constant)
- `READER_CLEANUP_LINEAGE_DIR` — 2 sites (Cluster B constant)

**Two distinct monkeypatch situations, handled differently:**
1. **Patched name whose in-module CALLER stays in `late_phases`** (e.g. `collect_recent_...` read by
   `run_docx_build_phase`): a re-export (`from newmod import name`) into `late_phases` is sufficient — the caller
   reads `late_phases`'s global, `monkeypatch.setattr(late_phases, name, …)` rebinds it, patch lands. Keep the caller
   referencing the bare re-exported global.
2. **Patched name whose CALLER also MOVES** (e.g. `QUALITY_REPORTS_DIR` read by `_write_quality_report_artifact`,
   both moving to the new module; same for `READER_CLEANUP_LINEAGE_DIR`): the re-export does NOT propagate — the moved
   function reads the NEW module's global, so patching `late_phases.<const>` misses it. These test sites MUST be
   repointed to patch the new module (exactly the compat-seam propagation lesson). This is the trap the first-scoped
   plan missed.

**General mechanism for every step:** move symbols to `pipeline/<newmod>.py`; add `from .<newmod> import <symbols>
# noqa: F401 re-export` in `late_phases.py` so `late_phases.<name>` keeps resolving (harness + test namespace +
situation-1 monkeypatch). For situation-2 patched constants, migrate the patching tests to the new module in the same
commit. `test_script_contract_static.py:335` hard-codes the file path `"src/docxaicorrector/pipeline/late_phases.py"`
— update it if a moved symbol invalidates the check.

## Scope — staged, each step independently committable + behaviour-preserving

**Step 0 — characterization goldens (no move).** Drive the module offline (fake `dependencies`/`emitters`/`state`,
`generate_markdown_block` returns canned text) and snapshot: `_build_translation_quality_report` over the pass /
hygiene-fail / manual-review / untranslated-body / TOC-concat / controlled-fallback matrix; `build_report_acceptance_verdict`;
`_resolve_document_delivery_verdict` transitions; the reader-cleanup registry/identity/markdown outputs (Cluster B);
Cluster A normalizers; and a `finalize_processing_success` end-to-end recording-fake test asserting the ordered
emit/artifact sequence for success / gate-fail / reader-cleanup-deferred paths. Add a **monkeypatch-contract regression
test**: patch `late_phases.collect_recent_formatting_diagnostics_artifacts` and assert `run_docx_build_phase` observes
it (pins the re-export requirement). Add Cluster E retention tests (age/count pruning). Commit — this is the safety net.

**Step 1 — Cluster E → `pipeline/quality_report_retention.py`.** Move `QUALITY_REPORTS_DIR`/`…MAX_AGE`/`…MAX_COUNT`,
`_prune_quality_reports`, `_write_quality_report_artifact`. Re-export into `late_phases`. **Migrate the 17
`QUALITY_REPORTS_DIR` patch sites to the new module** (situation 2). Verify.

**Step 2 — Cluster D → `pipeline/formatting_diagnostics_feedback.py`.** Move the 5 fns. Keep `run_docx_build_phase`
calling `collect_recent_...` as a re-exported `late_phases` global (situation 1 — no test change). Verify the
monkeypatch-contract test.

**Step 3 — Cluster J → `pipeline/narration_postprocess.py`** (+ shared `_resolve_text_call_target` /
`_require_group_int` into `pipeline/text_call_support.py`). Re-export test-referenced names. Verify.

**Step 4 — Cluster B → `pipeline/reader_cleanup_rebuild.py`.** Move the 259–1039 block + `READER_CLEANUP_LINEAGE_DIR`
+ `ReaderCleanupPostprocessResult`. Re-export all harness- and test-referenced privates. **Migrate the 2
`READER_CLEANUP_LINEAGE_DIR` patch sites** (situation 2). Harness can stay unchanged (re-export). Verify with the
harness script + tests.

**Step 5 — Cluster C → `pipeline/reader_cleanup_postprocess.py`** (`_run_reader_cleanup_postprocess`, imports B + text_call_support). Re-export. Verify.

**Step 6 — Cluster A → `pipeline/runtime_display_markdown.py`.** Re-export test-referenced names. Verify.

**Step 7 — Cluster G → `pipeline/terminal_results.py`** (`_emit_terminal_result`, `emit_failed_result`,
`emit_stopped_result`, `fail_empty_processing_plan`). Re-export. Verify.

**Step 8 — Cluster F → `pipeline/quality_gate.py`** (the ~1550-line core; optionally 8a detectors/serializers/thresholds
+ 8b the `_build_translation_quality_report` hub + acceptance + authority/warning). Re-export every test-referenced
name. Verify against the Step-0 golden matrix — this is where the goldens earn their keep.

**Step 9 (optional) — Cluster H → `pipeline/build_phases.py`.** **Step 10 — residual:** `late_phases.py` = `finalize`
(Cluster I) + the re-export shim. Optionally migrate `_pipeline.py` imports to the real modules and drop the shim in a
final dedicated commit.

## Test plan

After EVERY step: `test_document_pipeline.py`, `test_gate_detectors_stage2.py`, `test_real_document_pipeline_validation.py`,
`test_document_pipeline_output_validation.py`, `test_processing_service.py`, `test_script_contract_static.py`, plus the
new characterization goldens — all green, no golden diff. Harness script runs after Step 4.

## Out of scope

- Behaviour changes of any kind (byte-identical relocation + re-export only).
- The other four large modules (`reader_cleanup_mvp/service.py`, `generation/formatting_transfer.py`,
  `validation/structural.py`, `pipeline/output_validation.py`) — separate specs 032-035.

## Non-goals

(See also `## Out of scope` above.)

- No behaviour change of any kind — byte-identical relocation + re-export only.
- The other four large modules (`reader_cleanup_mvp/service.py`, `generation/formatting_transfer.py`, `validation/structural.py`, `pipeline/output_validation.py`) are out of scope — specs 032-035.

## Anti-regression

- The Step-0 characterization goldens (translation-quality-report matrix, `build_report_acceptance_verdict`, delivery-verdict transitions, Cluster A/B outputs, and the `finalize_processing_success` ordered emit/artifact sequence) stay byte-identical after EVERY extraction step — tests/test_late_phases_characterization.py.
- The monkeypatch contract survives the moves: patching `late_phases.collect_recent_formatting_diagnostics_artifacts` is still observed by `run_docx_build_phase` (situation-1 re-export), and the situation-2 constants are patched on the NEW module — tests/test_late_phases_characterization.py (monkeypatch-contract regression test) + test_document_pipeline.py + test_script_contract_static.py.

## SaaS rationale

Neutral; a cohesive, testable pipeline layer is easier for a backend/worker to reuse and maintain.
