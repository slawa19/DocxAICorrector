# Feature Specification: Review round-3 findings remediation (correctness + boundaries + hygiene)

Date: 2026-07-16
Status: **PLANNED (2026-07-16).** Living findings register for the in-progress round-3
review of the SaaS-hardening branch. Every finding below was independently verified
against live code (file:line evidence cited) before entry. Remediation is NOT yet
implemented. The review is ongoing — new findings are appended here as they are
verified; unverified reported items sit in `## Pending verification` until confirmed.
Owner surface: quality-gate entrypoints, `validation/acceptance.py`,
`pipeline/output_validation.py`, `pipeline/quality_gate.py`, `processing/application_flow.py`
+ `runtime/state.py` seam, `pipeline/late_phases.py` finalize, `AGENTS.md`, `.gitignore`
+ tracked generated artifacts, and the layer/contract test suite.

Verification: each finding carries a VERIFIED evidence line (grep/read against the working
tree at commit `120c66c`). Remediation acceptance is defined per-finding under
`## Anti-regression`; nothing here is marked done until its anti-regression test lands green.
Changelog: 2026-07-16 — spec created; findings F1–F5 verified and entered; P2 refactors
(NEXT_ACTION #7) parked in `## Pending verification` pending independent confirmation.
2026-07-16 — F6 added from two verified test-actuality audits (book-specific determinism +
dead tests); net: 2 DELETE (dormant determinism test + orphaned image), 6 GENERALIZE in
lockstep with F2, remainder of the 90-module suite verified clean (0 permaskips/xfails/hollow).

## Problem

An independent multi-subagent round-3 review of the branch surfaced one P0 correctness
break, four P1 issues (Constitution VII literals, layer-boundary leakage, an observability
contract gap), and a cluster of P1/P2 docs/repo-hygiene defects. The subagents reported no
material conflicts; the architecture and validation slices independently converged on the
same root class: **production/shared validation carries document-specific literals and
smears harness/prod ownership.** This spec records the verified findings and their intended
remediation so they can be scheduled and gated by tests, independently of the still-running
review.

## Confirmed findings (verified against live code)

### F1 — P0 — Broken canonical real-document quality-gate entrypoint
- VERIFIED: `scripts/run-real-document-quality-gate.sh:7` runs
  `exec bash scripts/test.sh tests/test_real_document_quality_gate.py -vv -s`, but
  `tests/test_real_document_quality_gate.py` **does not exist** (present siblings:
  `test_real_document_pipeline_validation.py`, `test_real_document_validation_corpus.py`).
  `.vscode/tasks.json:411` chains to it via `command: "bash scripts/run-real-document-quality-gate.sh"`.
- Impact: the advertised real-document quality gate errors at pytest collection (file not
  found) before any check runs — a task that looks runnable but never validates.
- Remediation: restore the missing selector OR repoint script + VS Code task + any docs to
  the actual canonical test; do NOT leave a dangling selector.
- Constitution: correctness / "the gate that claims to guard must actually run."

### F2 — P1 — Production validation carries document-specific literals (Constitution VII)
- VERIFIED: `src/docxaicorrector/validation/acceptance.py:436` —
  `"lietaer_exchange_install_roof_split": "установить\n\nустановить новую крышу"` (a
  per-book literal; 15 `lietaer` occurrences across `src/`).
- VERIFIED: `src/docxaicorrector/pipeline/output_validation.py:2120-2135` —
  `collect_theology_style_issue_samples` hardcodes book/domain strings
  `"Суд над пятым печатью"`, `"Четвёртое чашеобразное судилище"` and the glossary tuple
  `("imago dei", "koinonia")`.
- Impact: these live in shared/production validation, not fixtures — they false-gate other
  documents, do not generalize, and carry no provenance.
- Remediation: move per-book/per-domain literals into fixture-only regression tests, OR
  replace with a source-backed / domain-configured mechanism that records provenance and is
  covered by anti-vacuum tests (the mechanism must not silently pass when its config is empty).

### F3 — P1 — Blurred layer boundaries (Streamlit in processing core; pipeline→private validation)
- F3a VERIFIED: `src/docxaicorrector/processing/application_flow.py:1-5` declares the module
  "ui-free" and "must NOT import the `ui` package", but `:38` imports
  `from docxaicorrector.runtime.state import ...`, and `runtime/state.py:15` does an
  unconditional module-level `import streamlit as st`. So importing the processing core
  transitively imports Streamlit. `tests/test_layer_boundaries.py` only forbids the `ui`
  package, so this slips through.
- F3b VERIFIED: `src/docxaicorrector/pipeline/quality_gate.py:16-23` imports several
  `validation.*` helpers; `:2046-2071` does a deferred `from docxaicorrector.validation import
  structural` and calls the **private** `_derive_toc_body_concat_gate_fields(...)` and
  `_derive_unit_aware_unmapped_fields(...)`.
- Impact: a headless/backend worker cannot import processing without Streamlit; and the
  pipeline reaches into private validation internals (ownership smear, fragile coupling).
- Remediation: (a) introduce a session adapter/ports seam so the processing core no longer
  imports `runtime.state`/Streamlit; (b) split the shared pure gate math into a neutral leaf
  module with no imports from `processing`/`pipeline`, and expose a public API from
  `validation.structural` instead of the `_`-prefixed helpers.

### F4 — P1 — Successful run can finish without UI artifacts (observability contract)
- VERIFIED: `src/docxaicorrector/pipeline/late_phases.py:904-911` — on `OSError` while saving
  UI result artifacts it only logs `WARNING ui_result_artifacts_save_failed` (no re-raise, no
  state change); `:965-971` then calls `emitters.emit_finalize(..., "completed")` and `:973`
  logs `processing_completed` **unconditionally** (the finalize emit is outside the
  try/except/else). A run that failed to save artifacts still reports `completed` without any
  `ui_result_artifacts_saved`.
- Impact: violates the artifact observability contract — downstream (UI, segment registry,
  future backend consumers) sees success while the result files are absent.
- Remediation: make the save failure terminal-visible — either fail the run or emit an
  explicit completed-with-warning that signals the missing artifacts; never a silent
  `completed` without a corresponding `ui_result_artifacts_saved`.

### F5 — P1/P2 — Docs & repo hygiene create false routes
- F5a VERIFIED: `AGENTS.md:387` (a mandatory pre-hypothesis step) points to
  `docs/specs/STRUCTURE_RECOGNITION_COMPLETION_PLAN_2026-05-14.md`, which is **absent** there —
  the file actually lives at `docs/archive/specs/STRUCTURE_RECOGNITION_COMPLETION_PLAN_2026-05-14.md`.
  The two docs referenced at `AGENTS.md:395`
  (`TOPOLOGY_FIRST_STRUCTURE_RECOVERY_REMEDIATION_SPEC_2026-05-12.md`,
  `LAYOUT_SIGNAL_EVIDENCE_SLICE_SPEC_2026-05-14.md`) are likewise absent under `docs/specs/`.
- F5b VERIFIED: `AGENTS.md:395` tells agents to gate Stage-1 changes behind "a separate
  approved spec under `docs/specs/`", which **contradicts** `AGENTS.md:18-21`
  ("`specs/<NNN>-<slug>/` … ALL new specs go here" and "`docs/specs/` … Create NO new spec here").
- F5c VERIFIED: 44 files are tracked under `benchmark_projects/pdf_candidate_benchmark/artifacts/`,
  which `.gitignore:49-50` labels "Generated benchmark artifacts" (`.../artifacts/**`) — tracked
  generated output.
- F5d VERIFIED: `paradump.txt` (289 KB) is tracked at the repo root and reads like a stray dump.
- Remediation: repoint the stale `AGENTS.md` links to the archive (or restore the docs);
  reconcile the `:395` vs `:18-21` spec-home contradiction; untrack the generated benchmark
  artifacts (`git rm --cached`, keep them generated) or move them out of the ignored path;
  decide the fate of `paradump.txt` (remove or relocate).

### F6 — P2 — Book-specific determinism & one orphaned fixture in tests (audit-driven)
Two parallel test-actuality audits (book-literal axis + dead-test axis), each verified against
live code:
- **Dead determinism (DELETE):** `tests/test_real_document_pipeline_validation.py:788-846`
  (`test_collect_paragraph_break_samples_is_deterministic_on_saved_reports`) hardcodes per-book
  counts `{"money":6,"lietaer":13,"mazzucato":2,"creatingwealth":6}` plus exact source-index
  pins against four run-report dirs (`20260710T_lietaer_anchors`, `20260711T_money_marker`,
  `20260710T_mazzucato_listctx`, `20260710T_creatingwealth_fixed`) — VERIFIED absent; the test
  `pytest.skip`s at :807-809 whenever they are missing, i.e. it is **dormant on every clean
  checkout/CI**. Delete, or re-anchor to a committed report and re-derive the counts.
- **Orphaned fixture (DELETE):** `tests/artifacts/lietaer_image7.jpeg` is git-tracked with ZERO
  references anywhere in the repo (VERIFIED `git grep` empty). Remove.
- **Book-specific literals — GENERALIZE in lockstep with F2:** the theology/glossary literals of
  the source-less book "Are We In The End Times" (VERIFIED absent from `tests/sources/book/`,
  which holds only 5 maintained books) are asserted directly in tests —
  `test_document_pipeline_output_validation.py:983-995`, `test_document_pipeline.py:3899-3925` &
  `:3944`, `test_output_validation_characterization.py:177` (+ golden
  `fixtures/output_validation_characterization/collect_samples.json`) — and the Lietaer
  single-incident twin `lietaer_exchange_install_roof_split` at
  `test_real_document_pipeline_validation.py:1437-1438`. These are the test-side twins of the F2
  production hardcode; remove/generalize them together with F2 so a general detector replaces the
  per-book string matches. (Borderline domain-general normalizer tests that merely use
  End-Times-derived sample sentences — e.g. scripture-reference heading recognition — may keep
  the behaviour and only de-theologize the sample text.)
- **Confirmed clean (KEEP):** the audit found NO permanent skips (all skips env/offline-gated),
  NO xfail markers, NO removed-symbol / hollow / vacuous tests, and NO missing-fixture references
  across all 90 test modules (`pytest --collect-only` = 1999 tests, 0 import errors). Fixture-backed
  provenance goldens (e.g. `test_preserve_authored_tables.py` corpus pins; formatting-mapper
  goldens loaded via dynamic slug from `tests/sources/book/*.docx`) stay.

## Scope — remediation order (severity-first)

1. **F1 (P0) first** — restore/repoint the quality-gate selector so the gate runs.
2. **F4** — make artifact-save failure terminal-visible.
3. **F2** — de-literalize production validation (fixtures or provenance-backed config).
4. **F3b** then **F3a** — neutral leaf gate module; then decouple Streamlit from processing.
5. **F5** — docs + repo hygiene.
6. **Pending P2** — only after the above and after independent verification (see below).

Each item lands with its anti-regression test in the same commit as the fix.

## Test plan

Per finding, add/extend the guard tests listed in `## Anti-regression`, plus re-run the
existing contract/boundary suites: `tests/test_script_contract_static.py`,
`tests/test_layer_boundaries.py`, `tests/test_documentation_links.py`,
`tests/test_document_pipeline.py`, and the real-document validation suites. Run each touched
file via the WSL runner (`scripts/test.sh tests/<file>.py -q`) and the full suite before
declaring any finding closed.

## Pending verification (round-3 continuing — NOT yet confirmed)

Reported by the review but not yet independently verified; do not action until confirmed and
promoted into `## Confirmed findings`:
- P2: `document.extraction -> processing_runtime` dependency direction.
- P2: `core.config -> image/text` imports (config depending on feature modules).
- P2: duplicated `_ensure_src_first_import_order` helper.
- The `.gitignore` negation nuance for F5c (`!.../artifacts/` re-includes the directory, so
  `git check-ignore` reports the tracked manifest as not-ignored) — confirm the intended
  final state (fully ignored vs. curated-tracked subset) with the owner before mass-untracking.

## Out of scope

- Implementing any remediation in this spec (this is a verified findings register; fixes land
  under their own commits/spec sections as scheduled).
- The still-open monetization decision and any spec under `plans/` (owner-held).
- Behaviour changes beyond what each remediation explicitly requires.

## Non-goals

(See also `## Out of scope`.)

- NOT a redesign of the validation architecture — F2/F3 remediation is the minimum to remove
  document-specific literals and the Streamlit/private-helper coupling, not a rewrite.
- NOT a full repo line-ending/hygiene sweep — F5 covers only the verified false-route items.
- NOT a claim that the round-3 review is complete; the register stays open.

## Anti-regression

- **F1:** a static contract test asserting every `tests/*.py` path referenced by `scripts/*.sh`
  and `.vscode/tasks.json` exists (extend `tests/test_script_contract_static.py`). It fails on
  today's dangling `test_real_document_quality_gate.py` reference and passes once repointed.
- **F2:** a test scanning production validation modules (`validation/`, `pipeline/output_validation.py`,
  `pipeline/quality_gate.py`) for book/domain literals (deny-list incl. `lietaer`, the theology
  headings, the glossary terms); plus, for any retained config-driven mechanism, provenance +
  anti-vacuum assertions (empty config must not silently pass).
- **F3:** extend `tests/test_layer_boundaries.py` to forbid a `streamlit` import anywhere below
  the UI/adapter layer (catches the `processing → runtime.state → streamlit` chain); add a test
  forbidding `pipeline.*` from importing `_`-prefixed symbols out of `validation.*`.
- **F4:** a finalize test that injects a failing `write_ui_result_artifacts` and asserts the
  terminal emit reflects the failure (not a clean `completed`, and no `ui_result_artifacts_saved`
  without the files).
- **F5:** extend `tests/test_documentation_links.py` to validate `AGENTS.md` internal path
  references (fails on the stale `docs/specs/...` link); add a test asserting no tracked files
  exist under the "Generated …" ignored artifact paths; assert `paradump.txt` is not tracked.
- **F6:** delete the dormant determinism test (#788-846) and the orphaned `lietaer_image7.jpeg`;
  when the F2 detector is de-literalized, regenerate/remove the theology characterization golden
  and drop the inline book-literal assertions; add a guard test that fails if any test asserts on
  the known source-less book literals (shared deny-list with F2), so per-book determinism cannot
  creep back into the suite.

## SaaS rationale

Directly load-bearing for the external admin-panel / worker future: F1 restores the guard that
must run in CI; F2 removes per-book literals that would false-gate other tenants' documents;
F3 is what lets a headless backend import the processing core without Streamlit; F4 keeps the
"completed" signal honest for downstream consumers; F5 removes dead routes that mislead agents
and bloat the repo.
