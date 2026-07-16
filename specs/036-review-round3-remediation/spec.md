# Feature Specification: Review round-3 findings remediation (correctness + boundaries + hygiene)

Date: 2026-07-16
Status: **PARTIALLY IMPLEMENTED — round-4 review reopened gaps (2026-07-16).** The initial pass
below landed all F1–F28 across 8 waves with green tests, but a follow-up (round-4) review found
that several fixes satisfied their unit test WITHOUT closing the runtime/evidence contract
(P0 gate self-failure now fixed in `9274619`; plus real gaps in F2 dead-axis, F3 `processing_service`
still streamlit-bound, F7 non-killing PDF timeout, F13 corpus-calibrated ratio, F16 env-name-not-secret
cache key, F25 two missed retry sites, F27 preparation stage ungated, and others). The round-4
findings + their true-contract remediation are tracked as a follow-up increment (see the end of this
spec). Do NOT treat F1–F28 as fully closed. Initial-pass detail follows.

Prior (initial-pass) claim: All findings F1–F28 were independently verified against
live code (file:line evidence) and then remediated across 8 orchestrated waves (branch
`hardening/wave1-saas-prereqs`, commits `faa9bf7`…`573e70e`), each landing with its
anti-regression test and the pyright ratchet held at 247. One scope decision is recorded and
respected: the F28b hub decomposition split `quality_gate.py` (satellites extracted, core pinned)
but **left `generation/formatting_mapping.py` intact** — decomposing the correctness-critical
mapper would reverse the deliberate spec-029/033 decision, so it was not done. Per-finding
outcomes + commits are in `## Implementation status`.
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
2026-07-16 — F7–F28 added from the full round-3 code review (6-subagent verification + my own
spot-checks against 96a3a34). All confirmed except three honestly-narrowed: F13 (scan-origin —
spec 020 mitigates authored case), F23 (heading promotion — the "ordinal body text" sub-claim
REFUTED as typography-gated), F28 (the "13 specs" and ">650-line functions" claims REFUTED —
actually 1 spec missing Anti-regression, largest function exactly 650). Extensions folded into
F2–F5; remediation re-cast into a 6-phase plan; `_ensure_src_first_import_order` promoted from
Pending to F5 (7 defs confirmed).
2026-07-16 — ALL findings implemented across 8 waves (`faa9bf7`…`573e70e`); status → IMPLEMENTED.
Each fix landed with its anti-regression test; pyright ratchet held at 247 throughout (a mid-sweep
drift to 305 was reconciled back by proper typing, 0 `# pyright: ignore`). See `## Implementation status`.

## Implementation status

All 28 findings remediated on branch `hardening/wave1-saas-prereqs`. Commit map:

- **`faa9bf7`** — F1 (quality-gate selector repointed + selector-existence contract test), F18
  (structural-diagnostic task argv), F20 (CI runs the full static tier), F21 (dead AI-structure
  workflow retired), F22 (Docker CI parity via read-only-mount script), F28a (spec 017 Anti-regression).
- **`5b5f23a`** — F5 (stale AGENTS/COPILOT links → archive + `:395` contradiction reconciled;
  doc-link checker widened; 7 `_ensure_src_first_import_order` copies → one `docxaicorrector_bootstrap`;
  `paradump.txt` removed; 44 generated benchmark artifacts untracked).
- **`14c9393`** — F4 (artifact-save failure → distinct `processing_completed_unpersisted` + user
  notice, result still delivered from state), F10 (re-gate the delivered post-cleanup markdown).
- **`efc9bea`** — F14 (prep cache key fingerprints language/domain/structure-recovery), F15
  (resolvers honor passed `app_config`), F16 (provider-client cache keyed by full config fingerprint),
  F25 (compat adapters drop the TypeError retry).
- **`c99c7e7`** — F7 (PDF parse budgets), F8 (pre-decode image pixel/bomb budget), F11 (textbox-sibling
  image survives), F12 (PDF dropped-image counters + warning), F13 (per-table authored-signal scan
  decision), F23 (signal-gated heading promotion), F24 (heading emphasis runs preserved), F27
  (process-wide admission gate); pyright reconciled 305→247.
- **`ef257c1`** — F17 (retry after prep failure + reachable reset), F19 (readiness gates on the real
  `app.ready` marker), F26 (retention on segment/job registries + block-fallbacks); fixed a latent
  CI-breaker (new Wave-2 test file missing from `TEST_TIER_INVENTORY.md`).
- **`95f9c92`** — F2 (production validation de-literalized: theology detector config-driven with empty
  defaults, per-book acceptance dict removed, prompt examples neutralized), F6 (2 dead tests deleted,
  twins generalized to synthetic terms, Lietaer check → fixture regression, deny-list guard added).
- **`554fd0b`** + `3fe89b9` — F3 (UI-free `upload_ports`/`session_ports`; the processing/document
  core no longer transitively imports Streamlit, enforced by a fresh-subprocess boundary test) + a
  CRLF→LF normalization of `test_processing_runtime.py`.
- **`573e70e`** — F28b (extracted pure detector/serializer satellites from `quality_gate.py`
  2177→1982, byte-identical, core pinned; `formatting_mapping.py` intentionally NOT decomposed —
  see Status).

Honestly-narrowed sub-claims (implemented as the verified reality, not the overstated report): F13
(document scan-origin kept as a prior + per-table override, not a full rewrite), F23 (only the
text-only promotion paths gated; the ordinal path was already typography-gated), F28 (only spec 017
lacked Anti-regression; the mapper stays intact).

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

## Round-3 full-review findings — verified 2026-07-16 (F7–F28)

A six-subagent audit of all production/test/CI/docs surfaces plus my own spot-checks on the
load-bearing claims. Every finding below was VERIFIED against commit `96a3a34`; overstated or
refuted sub-claims are called out honestly so the register does not inflate scope.

### Extensions to existing findings (F2–F5)
- **F2 (+ reader prompt, lower severity):** `reader_cleanup_mvp/_prompts.py:74` carries
  book-derived few-shot EXAMPLE strings ("20 NEW FORMS OF MONEY?", "БЕСПЛАТНЫЕ КЛИНИКИ…",
  "Три мультинациональные валюты"). Unlike the F2 gating literals these merely teach a general
  cleanup skill, so this is a de-theologize-the-examples task, NOT a gating-correctness bug —
  keep it a distinct, lower priority.
- **F3 (+ concrete chain):** the transitive Streamlit import is `document/extraction.py:95` →
  `processing/processing_runtime.py:19` (unconditional `import streamlit as st`); the boundary
  test must ban transitive — not just direct — `streamlit` below the adapter layer.
- **F4 (+ succeeded):** the same fall-through also `return "succeeded"` (`late_phases.py:994`,
  `PipelineResult` at :194) and emits `processing_completed` — the run is reported *succeeded*,
  not merely "completed", despite the artifact-save failure.
- **F5 (+ doc coverage + dup helper, now confirmed):** the doc-link checker
  `test_documentation_links.py:22` covers only 2 docs, so `docs/COPILOT_CLI_LOOP_USAGE.md:65`
  references a non-existent `src/docxaicorrector/ui/structure_review_panel.py` unguarded; and
  **7** standalone entrypoints duplicate `_ensure_src_first_import_order` (VERIFIED defs in
  `scripts/run_pic1_modes.py`, `scripts/_run_cleanup_now.py`,
  `tests/artifacts/real_document_pipeline/run_lietaer_validation.py`, `tests/conftest.py`, and
  the three `benchmark_projects/*/benchmark_runner.py`) — promoted from Pending verification.

### P1 — data safety / resource / correctness
- **F7 (P1) — PDF parse has no resource budget.** `processing_runtime.py:478-516` +
  `pdf_import/images.py:41` run pdfminer fully in-process with no page/object/span/pixel/
  wall-clock cap (the only timeout, 120s, guards solely the ocrmypdf side-path). A small
  adversarial/bomb PDF can exhaust RAM/CPU. → isolated worker + page/time/size budgets.
- **F8 (P1) — raster decoded before any pixel budget.** `image/analysis.py:481-490` &
  `image/generation.py:147-151` call `Image.open(...).load()` before any check (only a *lower*
  80px bound afterward); no `MAX_IMAGE_PIXELS`/bomb guard, and `DecompressionBombError` would be
  swallowed by the broad `except`. → header-level width/height/megapixel/decoded-byte check
  before `.load()` + per-document aggregate budget.
- **F9 (P1, Constitution VII) — provenance-free paragraph merge.** `output_validation.py:1326`
  merges two entries when `_left_entry_looks_incomplete && _right_entry_looks_like_continuation`
  (pure punctuation/case/Russian-template heuristics), gated only by block adjacency
  (`same_block`/`adjacent_cross_block`, :1309-1310) — NOT by `source_index`/`paragraph_id`/
  `boundary_source`, which the entries carry but the merge never reads. Two distinct source
  paragraphs can be fused. → require shared source origin or an explicit boundary relation.
- **F10 (P1) — quality gate runs on pre-cleanup markdown.** `late_phases.py:586` computes the
  only `_build_translation_quality_report` on `gate_input_markdown = assembly_result.final_markdown`
  (:577); reader-cleanup runs AFTER (:699) and replaces the delivered artifacts (:712-713) with
  no re-gate. So a fixable result is rejected AND a cleanup-introduced regression ships "passed".
  → recompute the final gate on the delivered post-cleanup markdown/DOCX.
- **F11 (P1) — image lost when host paragraph also has a textbox.** `extraction.py:434-435`
  sets `include_image_placeholders = not has_textboxes` for the WHOLE paragraph; when a textbox
  is present, `_extract_run_image_placeholders` (the sole `ImageAsset` capture, :1386-1403) is
  skipped, and the restore pass only revisits `w:txbxContent` interiors — a direct sibling image
  is truly lost. → XML-walk direct drawings excluding only `w:txbxContent` descendants.
- **F12 (P1) — PDF images silently dropped, uncounted.** `pdf_import/images.py:45-49,100-103`
  `continue`/swallow on empty stream / unknown MIME / decode error with no discovered-vs-emitted
  counter; the caller logs only survivors + append-step drops, so extraction-time image loss is
  invisible. → discovered/emitted/dropped-by-reason counters + terminal warning when discovered>emitted.
- **F13 (P1, PARTIAL) — scan-origin is a global threshold, not per-table.** `provenance.py:59-72`
  returns one document-level `is_scan_origin` from corpus thresholds (`ABSOLUTE_MIN=10`,
  `RATIO_MIN=0.10`); `extraction.py:386-390` then flattens EVERY table when true. Spec 020's `else`
  branch preserves authored tables, so the common case is mitigated — but an authored multi-column
  doc that trips the thresholds still loses ALL real tables. → decide per-table from local signals.
- **F14 (P1) — prep cache key omits language/domain/structure-recovery.** VERIFIED key
  (`preparation.py:288-293`) = `token:chunk:boundary:ai_review:relation:lc:op:pv` — excludes
  source/target language, `translation_domain` (+ derived glossary/style, :532/:547-548/:423-426)
  and structure-recovery params, all of which shape the cached result. Cross-run glossary/context
  bleed. → versioned fingerprint of all influencing settings.
- **F15 (P1) — passed `app_config` partially ignored.** `extraction.py:209/:259/:267`
  boundary/relation/AI-review resolvers call `load_app_config()` (global) instead of the passed
  config (contrast layout-cleanup/structure-recovery/repair which DO honor it), so a validation
  override enters the cache key but not behavior. → thread an immutable preparation config down.
- **F16 (P1) — provider client cache keyed by name only.** `core/config.py:1427/1464`
  `_CLIENTS_BY_PROVIDER[normalized_provider_name]` ignores base_url/default_headers/timeout/
  credentials (which DO shape the client, :1450-1458). A second call with different config reuses
  the stale client. → key on a fingerprint of the full resolved client config.

### P1 — workflows / UI / CI
- **F17 (P1) — retry blocked after prep failure; reset unreachable.** `runtime/state.py:275`
  `should_start_preparation_for_marker` returns false while `failed_marker == upload_marker`
  (no auto-retry), and `ui/_app.py:794-801` early-`return`s in the failed branch before the reset
  button at :826-828 renders. → explicit Retry that atomically clears the failed marker.
- **F18 (P1) — structural-diagnostic VS Code task args rejected by argparse.**
  `.vscode/tasks.json:438` passes `"…ProfileId" "…RunProfileArg"`; the run-profile input defaults
  empty and its description glues `--run-profile-id <id>` into one token, so empty→stray positional
  and populated→unsplit token; `structural.py:1065-1066` defines one positional + a separate flag.
  → inject the flag as separate argv, omit when empty.
- **F19 (P1) — readiness ignores the `app.ready` marker.** `project-control-wsl.sh:478-490`
  `wait_ready` gates on `health_ok && app_page_ok`, and `app_page_ok` (:156-168) matches only the
  static Streamlit shell; the real `app_ready()` (:170-172, marker written at :437) is used only as
  advisory output. Status can flip READY before render. → add `app_ready` to `wait_ready`.
- **F20 (P1) — CI never runs 4 static guards.** `.github/workflows/ci.yml:70` runs only
  `test_script_contract_static.py`, then :73 runs the suite with `-m "not static_workflow …"`, so
  the other four `static_workflow` files — `test_network_hardening_defaults`, `test_layer_boundaries`,
  `test_documentation_links`, `test_dependency_consistency` — NEVER execute in CI (VERIFIED: the
  marker covers exactly those 5 files). This silently un-guards the very contracts specs 022/036
  add. → run all static-tier files in CI.
- **F21 (P1) — AI-structure smoke workflow calls a deleted test.**
  `real-document-ai-structure-smoke.yml:44` invokes
  `tests/test_real_document_structure_recognition_integration.py` (VERIFIED absent); docs
  (`REAL_DOCUMENT_VALIDATION_WORKFLOW.md:132`) mark it removed while the workflow stays dispatchable,
  and `test_script_contract_static.py:220` PINS the stale invocation string. → retire the workflow +
  its contract assertions, or restore the test; reconcile the doc.
- **F22 (P1) — Docker CI Parity ≠ CI.** `.vscode/tasks.json:257` runs `pip install -r requirements.txt
  && pytest tests/ -q`; real CI does editable `.[dev]` install + pyright ratchet + separate static
  tier + marker exclusions. Green Docker ⇏ green CI (and it runs markers CI skips). → mirror CI or
  rename debug-only.

### P2 — architecture / ops / correctness
- **F23 (P2, PARTIAL) — literal heading promotion without a source signal.**
  `logical_import.py:1544` (`_looks_like_chapter_heading`, regex `^chapter …`) and the
  `_SECTION_MARKER_WORDS` list incl. "conclusion" (:1361-1372 → promote at :1496-1501) assign
  heading role from text alone. REFUTED sub-claim: the "ordinal-like body text" path is typography-
  gated (`_looks_like_numbered_section_heading` requires font prominence), so it does NOT promote on
  text alone. → gate Chapter/section-marker promotion on ≥1 layout signal, or sanction+document them.
- **F24 (P2) — heading emphasis dropped.** `processing_runtime.py:573-574` the heading branch does
  `add_run(paragraph.text); return` before the body-only `pdf_emphasis_runs` loop (:580-590), so
  mixed bold/italic in a heading is flattened. → apply the emphasis loop in the heading branch too.
- **F25 (P2) — compat adapters retry on TypeError.** `preparation.py:313-321` (and :329-339,
  :348-361) `try build_editing_jobs(**kwargs) except TypeError: build_editing_jobs(max_chars=…)` —
  despite already computing `inspect.signature` support flags — so an internal TypeError is masked
  as a signature fallback and mutating side effects run twice. → call once on the signature-checked
  kwargs; let internal TypeErrors propagate.
- **F26 (P2) — data-bearing artifacts with no retention.** `artifacts.py:364-415`
  `write_segment_result_registry`/`write_job_result_registry` and `block_execution.py:34-69`
  `.run/block_fallbacks` write with NO pruning (contrast `write_ui_result…`:315 /
  `write_structure_manifest`:354 which prune). Observed: 24 050 job-result files;
  `.run/layout_parser_experiment` ~3.25 GB. → recursive TTL/count/byte budgets.
- **F27 (P2) — no process-wide admission limit.** `processing_runtime.py:1633-1659` spawns a
  per-session daemon worker with no global semaphore (VERIFIED: no `Semaphore|admission|max_concurrent`
  anywhere in `src`); N sessions multiply PDF RAM/subprocesses/API cost. → bounded admission gate.
- **F28 (P2, PARTIAL) — oversized hubs + one spec gap.** VERIFIED: `formatting_mapping.py` = **2932**
  lines, `quality_gate.py` = **2177** lines (larger than the review's ~2600/~2000 estimate); and
  exactly **1** active spec — `specs/017-ocr-stamp-furniture-detection` — is missing `## Anti-regression`.
  REFUTED: the "13 specs violate the format" claim (0 missing Non-goals, 1 missing Anti-regression of
  36 specs) and the ">650-line functions" claim (largest are exactly 650 / 649, none over). → add the
  section to spec 017; decompose the two hubs by responsibility (report calc/verdict/IO;
  mapping candidate-gen/scoring/selection), not mechanically by size.

### Downgraded / out of scope (per the review's own CONFLICTS + my checks)
- **PDF origin collision** → P3 advisory only (currently affects an advisory signal, not delivery);
  not elevated.
- **`restart_store` path read without confinement** → defense-in-depth, NOT a confirmed vuln: the
  current external path gives no client control over `storage_path`. Track, don't gate.
- **Page-relative anchors / VML / floating images** → out of scope; the README already limits
  floating/legacy-Word-layout support.

## Scope — remediation order (phased, severity-first)

Given the volume, remediation is a Spec Kit package of bounded phases (each finding lands with
its anti-regression test in the same commit):

1. **Phase 1 — gates & CI integrity first (P0/P1):** F1 (restore/repoint the quality-gate
   selector + assert all script/task/workflow selectors exist), F20 (CI actually runs the static
   tier), F21 (retire the dead AI-structure workflow + its pinned contract), F10 (final gate on the
   DELIVERED post-cleanup artifact), F4 (terminal artifact status — no `succeeded` without persist).
2. **Phase 2 — data-loss & cross-run isolation (P1):** F9 (provenance-gated merge), F11/F12
   (textbox-sibling + PDF dropped images), F13 (per-table scan decision), F14/F15/F16
   (prep-key / app_config / provider-client fingerprints), F24 (heading emphasis), F23 (signal-gated
   heading promotion), F25 (drop the TypeError retry).
3. **Phase 3 — resource safety (P1):** F7 (PDF page/time/size budget in an isolated worker),
   F8 (pre-decode pixel/byte budget), F27 (process-wide admission gate).
4. **Phase 4 — UI/runtime reliability & retention (P1/P2):** F17 (retry + reachable reset),
   F19 (app.ready readiness), F18/F22 (task/CI-parity fixes), F26 (recursive retention budgets).
5. **Phase 5 — bounded refactor:** F3 (UI-free upload/state ports + transitive-streamlit boundary
   test), F28 (decompose the two hubs by responsibility; add `## Anti-regression` to spec 017).
6. **Phase 6 — validation de-literalization & repo/test cleanup:** F2 (+ prompt examples), F6
   (delete the 2 dead-test items; generalize the book-literal twins in lockstep with F2), F5
   (docs coverage, stale links, tracked benchmark artifacts, `paradump.txt`, the 7 duplicate
   `_ensure_src_first_import_order`).

## Test plan

Per finding, add/extend the guard tests listed in `## Anti-regression`, plus re-run the
existing contract/boundary suites: `tests/test_script_contract_static.py`,
`tests/test_layer_boundaries.py`, `tests/test_documentation_links.py`,
`tests/test_document_pipeline.py`, and the real-document validation suites. Run each touched
file via the WSL runner (`scripts/test.sh tests/<file>.py -q`) and the full suite before
declaring any finding closed.

## Pending verification (round-3 continuing — NOT yet confirmed)

Reported by the review but not yet independently verified; do not action until confirmed and
promoted into the findings above:
- P2: `core.config -> image/text` imports (config depending on feature modules) — NOT yet traced.
- The `.gitignore` negation nuance for F5c (`!.../artifacts/` re-includes the directory, so
  `git check-ignore` reports the tracked manifest as not-ignored) — confirm the intended
  final state (fully ignored vs. curated-tracked subset) with the owner before mass-untracking.

Resolved out of this section: `document.extraction -> processing_runtime` dependency is confirmed
and folded into F3 (the transitive-Streamlit chain); the duplicated `_ensure_src_first_import_order`
helper is confirmed (7 defs) and folded into F5.

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
- **F7/F8/F27 (resource):** unit tests that a synthetic over-budget PDF (page/object count) and an
  over-budget image (dimensions/megapixels, pre-decode) are rejected with a clear error before full
  parse/decode; a test that the admission gate caps concurrent workers.
- **F9:** a merge test proving two entries with non-contiguous `source_index` (no shared origin /
  no boundary relation) are NOT merged despite matching surface heuristics.
- **F10:** a finalize test asserting the quality gate is computed on the post-cleanup delivered
  markdown (a cleanup-introduced regression must fail the final gate).
- **F11/F12/F24:** extraction tests — image survives when its host paragraph also has a textbox;
  a PDF with an unknown-MIME image raises `discovered>emitted` warning/counter; a heading with
  mixed bold/italic keeps its emphasis runs in the DOCX.
- **F13:** an authored multi-column doc that trips the scan thresholds keeps its real tables
  (per-table decision), not flattened wholesale.
- **F14/F15/F16:** cache-isolation tests — differing language/domain/structure-recovery (F14),
  a passed `app_config` boundary/relation/AI-review override (F15), and differing provider
  base_url/timeout/headers (F16) each produce distinct cache entries / observable behavior.
- **F17/F19:** a Retry after prep-failure clears the marker and re-runs; readiness stays not-ready
  until `app.ready` exists.
- **F18/F20/F21/F22 (CI/tasks):** extend `test_script_contract_static.py` so every script/task/
  workflow-referenced test path exists (kills F1/F21 dangling refs) and task argv split is valid
  (F18); a CI-contract test asserting the static tier (`test_layer_boundaries`, `_documentation_links`,
  `_network_hardening_defaults`, `_dependency_consistency`) actually runs in `ci.yml` (F20); a
  parity assertion that the Docker task mirrors CI install/pyright/markers (F22).
- **F23/F25:** a heading-promotion test that `Chapter N`/`CONCLUSION` without a layout signal is
  NOT promoted; a compat-adapter test that an internal `TypeError` propagates (no silent double-call).
- **F26:** retention tests that segment/job registries and `.run/block_fallbacks` prune by
  age/count/bytes.
- **F28/F5:** a spec-format guard (already exists for Non-goals/Anti-regression) that flags spec 017;
  a test that no standalone entrypoint re-defines `_ensure_src_first_import_order` (single shared
  helper); expand `test_documentation_links.py` coverage so the `structure_review_panel.py` dangling
  reference fails.

## SaaS rationale

Directly load-bearing for the external admin-panel / worker future: F1 restores the guard that
must run in CI; F2 removes per-book literals that would false-gate other tenants' documents;
F3 is what lets a headless backend import the processing core without Streamlit; F4 keeps the
"completed" signal honest for downstream consumers; F5 removes dead routes that mislead agents
and bloat the repo.

## Round-4 follow-up register (2026-07-16) — remediated

A round-4 review found that several initial-pass fixes passed their unit test WITHOUT closing the
runtime/evidence contract. Each item below was re-verified against live code and remediated (branch
`hardening/wave1-saas-prereqs`); every fix landed with its anti-regression test and pyright held at
246. Commit map:

- **P0 gate self-failure** (`9274619`): the F1 gate script exports
  `DOCXAI_REQUIRE_REAL_DOCUMENT_CAPABILITIES=1`, but three default-skip meta-tests didn't clear the
  env → the gate failed on its own unit tests. Isolated the env in those three meta-tests only; the
  real corpus tests stay env-sensitive (verified: full gate module passes under env=1).
- **Batch 1 — security/runtime** (`a5bc1df`): F7 the PDF wall-clock guard now GENUINELY terminates
  (spawn multiprocessing child under one unified deadline covering page-count/spans/OCR/images;
  terminate→kill on overrun; caps on spans/images; in-process test seam) — the old daemon-thread
  guard never stopped the work and covered only the first stage. F27 the admission gate now covers
  PREPARATION (PDF parse/OCR), not just main processing, via a cancellable acquire. F8 the image
  pixel budget is now a real end-to-end GATE at every decode/base64/vision entry (oversized bytes
  never reach the API) + a per-document aggregate budget.
- **Batch 2 — evidence/isolation** (`64336e4`): Finding 8 the AUTHORITATIVE quality report is now
  rebuilt on the delivered post-cleanup markdown (verdict carried, stale artifact superseded) — and
  fixed an F10 trigger bug (display-hygiene vs reader-cleanup). Finding 6 removed the production-dead
  theology detector + wiring (count fields kept as documented inert constants for out-of-scope
  consumers). Finding 9 provider cache keyed on a sha256 of the RESOLVED secret (rotation re-keys);
  boundary-review uses the passed factory. Finding 5 completed F3 — `processing_service` no longer
  transitively loads Streamlit (new `service_ports`; boundary test extended).
- **Batch 3 — architecture/cleanup** (`fc58a47`): F11 retention never prunes the current run's own
  records + atomic writes. F12 primary-artifact vs registry/diagnostics persistence tracked
  separately. F10 prep cache key folds AI-review model/limits (pk=3). F15 quality_gate monkeypatch
  seam made coherent + proven. F16 mapper-golden perturbations keyed on stable source identity. F17
  nested-textbox images extracted exactly once. F13/F14 corpus/English literals moved to documented,
  config-overridable constants / an extensible lexicon (behaviour unchanged).

### Honest residuals (documented, not silently closed)
- **F13/F14 (Constitution VII):** the scan/table thresholds and heading-marker words are now named,
  documented, config-overridable constants rather than per-book literals — but structural detection
  still needs a *calibrated* signal, and the default heading lexicon is still English. A fully
  corpus-free / language-agnostic detector is genuine future work (documented in-source).
- **F15:** the pipeline's access to the PRIVATE `validation.structural._build_output_artifacts` is
  left with a TODO (a public wrapper would edit `validation/structural.py`, out of the batch scope).
- **F18:** several guards (readiness/CI-inventory/docs/deny-list) assert on strings/partial lists,
  not full runtime behaviour — a known limitation; this spec's Status was corrected from a premature
  "fully closed" claim to reflect that these are static contracts.
- A redundant `stash@{0}` WIP backup remains on the branch for the owner to `git stash drop` (the
  auto-approver refuses stash deletion without explicit authorization).
