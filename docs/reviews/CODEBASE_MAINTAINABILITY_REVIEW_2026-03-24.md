# Codebase Maintainability Review 2026-03-24

## 1. Scope and Method

Scope of this review:

- Active Python application modules in repository root.
- Validation and tooling Python modules under `scripts/` and `tests/artifacts/` when they materially affect architecture.
- Test suite structure under `tests/`.
- Operational config files that shape quality controls: `requirements.txt`, `pyproject.toml`, `pyrightconfig.json`.

Method used:

- Editor diagnostics: no current code errors were reported by workspace diagnostics.
- Import scan: direct project imports are narrow and coherent (`streamlit`, `dotenv`, `openai`, `docx`, `lxml`, `pypandoc`, `PIL`, `pytest`).
- Manual reading of key hotspots and layer boundaries.
- File size ranking to identify complexity hotspots.
- Targeted text search for duplicated placeholder contracts, stale APIs, and dead configuration fields.

Important limitation:

- This is a static review. I did not execute the full pytest suite as part of this report-only task. Test quality conclusions are based on file content, structure, names, and targeted spot checks.

## 2. Executive Summary

The project is in a better state than a typical fast-moving Streamlit codebase. It has clear domain clusters, meaningful tests, and recent architectural decomposition in the document pipeline. The main problem is not chaos; it is concentration of complexity in a small number of orchestration and pipeline modules.

The strongest parts:

- Clear separation between document extraction, formatting restoration, image reinsertion, image policy, and runtime event contracts.
- Good amount of regression coverage for real documents, restart behavior, workflow contracts, and startup constraints.
- Small, explicit data and event contracts in several places (`runtime_events.py`, `workflow_state.py`, `image_pipeline_policy.py`).

The highest-value cleanup opportunities:

- Reduce orchestration layering across `app.py`, `app_runtime.py`, `processing_runtime.py`, `processing_service.py`, and `document_pipeline.py`.
- Harden global singleton initialization in `config.py` and remove duplicated response-parsing logic.
- Split overloaded image-state structures and scoring logic.
- Remove or repair stale developer tooling (`scripts/run_pic1_modes.py`).
- Stop carrying dead config surface (`expected_acceptance_policy`) and low-signal spec-assertion tests.
- Add one minimal quality gate beyond pytest: lint plus stricter type checking for touched files.

## 3. Hotspots by Size

These are the largest Python files and therefore the most likely maintenance hotspots:

| File | Lines | Review note |
| --- | ---: | --- |
| `tests/artifacts/real_document_pipeline/run_lietaer_validation.py` | 2103 | Oversized validation runner; effectively a parallel runtime. |
| `tests/test_document.py` | 2030 | Valuable coverage, but too large for easy maintenance. |
| `tests/test_generation.py` | 1482 | Broad coverage, but should be split by concern. |
| `image_generation.py` | 1412 | Strategy-heavy module with multiple responsibilities. |
| `tests/test_document_pipeline.py` | 1360 | Strong but heavily mocked orchestration testing. |
| `document.py` | 1228 | Still large after decomposition; shared XML/helper bucket remains. |
| `generation.py` | 1184 | LLM prompting, retries, marker handling, Pandoc conversion in one file. |
| `document_pipeline.py` | 1162 | Protocol and orchestration hub with many implicit contracts. |
| `image_reconstruction.py` | 1072 | Large but relatively cohesive. |
| `formatting_transfer.py` | 1023 | High legitimate domain complexity; still tightly coupled to `document.py`. |
| `image_pipeline.py` | 989 | Orchestration mixed with scoring and candidate arbitration. |
| `processing_runtime.py` | 771 | Runtime queue, normalization, conversion, restart, and event draining in one file. |
| `ui.py` | 668 | Large rendering helper bucket with custom iframe theme synchronization. |

## 4. Priority Findings

### Critical

#### ARCH-001
- Paths: `app.py`, `app_runtime.py`, `processing_runtime.py`, `processing_service.py`, `document_pipeline.py`
- Category: architecture, over-abstraction, maintainability
- Problem: the application flow crosses too many indirection layers before real work happens. `app.py` still owns session/UI lifecycle and worker start logic; `app_runtime.py` is mostly a forwarding adapter; `processing_service.py` is a dependency-wiring facade; `document_pipeline.py` holds the actual orchestration contract.
- Impact: high change cost, harder tracing of failures, more places where contracts can drift silently.
- Business effect: slower delivery of new runtime/image features and higher regression risk in UI-to-pipeline changes.
- Fix complexity: medium
- Recommended strategy: keep `document_pipeline.py` as the orchestration core, but collapse one wrapper layer. The cleanest candidate is `app_runtime.py`, or alternatively shrink `processing_service.py` into a thinner factory plus explicit dependency bundle.

#### STALE-001
- Path: `scripts/run_pic1_modes.py`
- Category: stale code, broken tooling
- Problem: the script imports `app` and calls `app.process_document_images(...)`, but that API is not present in current `app.py`.
- Impact: developer tooling is misleading and likely broken on execution.
- Business effect: wasted debugging time during image-pipeline investigation.
- Fix complexity: low
- Recommended strategy: either remove the script if obsolete, or rewire it to `processing_service.get_processing_service().process_document_images(...)` or directly to `image_pipeline.process_document_images(...)` through a stable adapter.

### High

#### REL-001
- Path: `config.py`
- Category: reliability, concurrency
- Problem: `get_client()` uses module-level `_CLIENT` and lazy `OpenAI` import state without any locking. Under concurrent access, multiple threads can race and initialize more than one client instance.
- Impact: inconsistent singleton behavior and harder-to-debug startup/runtime races.
- Business effect: low-frequency but expensive operational bugs in threaded flows.
- Fix complexity: low
- Recommended strategy: add a lock and use the same double-checked initialization pattern already used in `processing_service.py`.

#### DUP-002
- Paths: `generation.py`, `image_shared.py`
- Category: duplication, maintainability
- Problem: response-shape helpers and text extraction logic for OpenAI Responses are duplicated across both modules, including `_read_response_field`, `_coerce_response_text_value`, `_extract_text_from_content_item`, and the main response text extraction flow.
- Impact: parser fixes or API-shape changes must be updated in more than one place, with a real risk of semantic drift.
- Business effect: slower integration with model API changes and more fragile retry/recovery behavior.
- Fix complexity: low
- Recommended strategy: keep one canonical implementation in `image_shared.py` and make `generation.py` consume it.

#### PERF-001
- Paths: `application_flow.py`, `processing_runtime.py`, `app.py`
- Category: optimization, duplication
- Problem: in `application_flow._prepare_run_context_core()` the synchronous path calls `build_uploaded_file_token(...)`, which itself normalizes a legacy `.doc`, and then calls `normalize_uploaded_document(...)` again. This can duplicate conversion work for legacy documents.
- Impact: unnecessary I/O, conversion latency, and complexity in the sync preparation path.
- Business effect: slower user-perceived restart/recovery or fallback flows, and more brittle conversion behavior.
- Fix complexity: low
- Recommended strategy: normalize once, then derive both token and payload from the normalized contract, or pass a precomputed normalized document into token generation.

#### DATA-001
- Path: `models.py`
- Category: architecture, data-model overload
- Problem: `ImageAsset` combines immutable source facts, mutable pipeline state, validation outcomes, attempt variants, comparison variants, and final delivery decision in a single mutable structure.
- Impact: high coupling across image modules and higher risk of partial-state bugs.
- Business effect: every new image mode or validation rule becomes harder to add safely.
- Fix complexity: medium
- Recommended strategy: split into `ImageSource`, `ImageProcessingState`, and `ImageDeliveryDecision` or an equivalent narrower composition while keeping current external behavior unchanged.

#### ARCH-002
- Paths: `real_document_validation_structural.py`, `tests/artifacts/real_document_pipeline/run_lietaer_validation.py`
- Category: architecture, duplication, validation debt
- Problem: the real-document validation layer partially re-orchestrates the runtime pipeline instead of only calling a single stable application boundary. The biggest example is `run_lietaer_validation.py`, which has become a second runtime in practice.
- Impact: drift between production flow and validation flow; expensive to evolve safely.
- Business effect: validator maintenance cost grows faster than product code.
- Fix complexity: medium
- Recommended strategy: define one reusable validation entrypoint around normalized input + prepared run context + pipeline execution, and make both validators consume it.

#### MOD-001
- Path: `image_pipeline.py`
- Category: duplication, complexity, architecture
- Problem: orchestration, candidate comparison, scoring (`score_semantic_candidate`), and delivery decisions live together. Policy already exists in `image_pipeline_policy.py`, but scoring/arbitration logic remains in the orchestration module.
- Impact: policy changes require editing the biggest moving part of the image pipeline.
- Business effect: slower tuning of image behavior and more subtle regressions.
- Fix complexity: medium
- Recommended strategy: extract candidate ranking and compare-all arbitration into a pure helper/policy module with deterministic tests.

#### UI-001
- Paths: `ui.py`, `app.py`
- Category: architecture, UI debt
- Problem: `ui.py` is large and contains a custom iframe theme-sync contract for markdown preview. This is a sign that the preview component boundary is not fully aligned with Streamlit’s native styling model.
- Impact: high UI fragility and harder UI evolution.
- Business effect: small UX changes are more expensive than they should be.
- Fix complexity: medium
- Recommended strategy: keep the existing component contract minimal, but isolate markdown preview into its own small module and centralize placeholder filtering and theme sync there.

### Medium

#### DUP-001
- Paths: `document.py`, `generation.py`, `ui.py`
- Category: duplication
- Problem: placeholder and paragraph-marker regex contracts are duplicated in multiple files.
- Impact: silent drift if placeholder syntax changes.
- Business effect: broken reinsertion or preview logic from contract mismatch.
- Fix complexity: low
- Recommended strategy: move all placeholder and marker regexes to one small shared contract module.

#### MOD-002
- Paths: `document.py`, `formatting_transfer.py`, `image_reinsertion.py`
- Category: coupling, hidden dependency
- Problem: `document.py` still exports private XML helpers and shared placeholder contracts that other modules depend on.
- Impact: `formatting_transfer.py` and `image_reinsertion.py` are more tightly bound to document internals than their names suggest.
- Business effect: harder to continue decomposition of the document pipeline.
- Fix complexity: medium
- Recommended strategy: extract a narrow `docx_xml.py` or `document_shared.py` helper module and move shared OOXML traversal helpers there.

#### DEAD-001
- Path: `real_document_validation_profiles.py`
- Category: dead code, dead config surface
- Problem: `expected_acceptance_policy` is parsed and validated, but no runtime path actually enforces it. Searches show the field exists only in profile parsing/tests.
- Impact: misleading API surface and false confidence in validation policy coverage.
- Business effect: wasted effort maintaining configuration that does not change behavior.
- Fix complexity: low
- Recommended strategy: either enforce it in validation policy checks or remove the field completely.

#### TEST-001
- Paths: `tests/test_spec_image_level1.py`, `tests/test_spec_image_followup.py`
- Category: test quality, low-signal regression coverage
- Problem: these tests assert headings and phrases inside archived spec documents rather than behavior of the running system.
- Impact: brittle noise during documentation edits, weak regression value.
- Business effect: higher maintenance cost with little protection of user-visible behavior.
- Fix complexity: low
- Recommended strategy: move them out of the main regression suite or replace them with behavioral tests around the image pipeline contracts they intend to document.

#### TEST-002
- Path: `tests/test_processing_service.py`
- Category: test quality, thin wiring
- Problem: much of the file validates event forwarding and delegation across mocked collaborators rather than business outcomes.
- Impact: low signal-to-maintenance ratio.
- Business effect: test volume grows without proportional confidence gain.
- Fix complexity: low
- Recommended strategy: keep only crash-isolation and event-contract tests that protect real runtime behavior; drop pure delegation assertions.

#### OPS-001
- Paths: `pyproject.toml`, `pyrightconfig.json`
- Category: tooling, maintainability
- Problem: the repository has pytest configuration and basic Pyright only. There is no configured lint gate such as Ruff, and type checking is intentionally permissive (`basic`).
- Impact: style drift, unused imports, and simple duplication can accumulate unnoticed.
- Business effect: higher cleanup cost later.
- Fix complexity: low
- Recommended strategy: add a minimal Ruff config and keep Pyright at least for touched files or changed modules in CI.

#### DUP-003
- Paths: `processing_runtime.py`, `state.py`
- Category: duplication
- Problem: image processing summary defaults are duplicated in `_build_default_image_processing_summary()` and `_default_image_processing_summary()`.
- Impact: minor today, but easy future drift in UI counters and reset behavior.
- Business effect: small maintenance tax on every summary-contract change.
- Fix complexity: low
- Recommended strategy: keep one canonical summary factory and import it in the other module.

#### DUP-004
- Paths: `preparation.py`, `processing_runtime.py`
- Category: duplication
- Problem: in-memory uploaded-file builders exist in both modules with the same responsibility.
- Impact: two places to update if upload-shape expectations change.
- Business effect: small but recurring maintenance friction.
- Fix complexity: low
- Recommended strategy: reuse the `processing_runtime.py` helper from `preparation.py` unless there is a real need for separate construction semantics.

### Low

#### MOD-003
- Path: `image_shared.py`
- Category: shared utility sprawl
- Problem: the module mixes MIME detection, retry logic, response-shape parsing, JSON extraction, score clamping, and error-code classification.
- Impact: it trends toward a catch-all shared module.
- Business effect: future image features are more likely to add cross-cutting utility debt.
- Fix complexity: medium
- Recommended strategy: split only when touching the module again: `image_api_utils.py`, `image_payload_utils.py`, `image_scoring_utils.py`.

#### OPS-002
- Paths: `requirements.txt`, runtime environment
- Category: reproducibility
- Problem: direct dependencies are minimal and reasonable, but only lower bounds are declared and there is no lockfile or constraints file.
- Impact: environment drift and harder debugging across machines.
- Business effect: inconsistent developer/runtime behavior.
- Fix complexity: low
- Recommended strategy: keep `requirements.txt`, but add a generated constraints file or documented known-good versions for CI/runtime.

#### REPO-001
- Paths: `tests/artifacts/real_document_pipeline/*.json`, `tests/artifacts/real_document_pipeline/runs/*`
- Category: repository hygiene
- Problem: large generated artifacts and JSON payloads with embedded object repr data pollute searches and increase review noise.
- Impact: slower code search and lower signal in repository-wide inspections.
- Business effect: minor, but recurring friction.
- Fix complexity: low
- Recommended strategy: keep canonical latest artifacts if required, but exclude bulky run outputs from default search or reduce embedded verbose payloads.

#### APP-002
- Path: `app.py`
- Category: maintainability
- Problem: `main()` still contains late imports and repeated end-of-frame cleanup calls (`_mark_app_ready()` and `_schedule_stale_persisted_sources_cleanup()`) in multiple branches.
- Impact: slightly harder control-flow review and more repetitive edit surface.
- Business effect: small, but contributes to UI orchestration friction.
- Fix complexity: low
- Recommended strategy: move imports to module scope where feasible and consolidate repeated tail actions behind one small helper.

#### GEN-001
- Path: `generation.py`
- Category: dead code, maintainability
- Problem: the duplicate `raise recovery_exc` branch is still present, which is small but unnecessary control-flow noise.
- Impact: negligible at runtime, but a sign that this module would benefit from light cleanup while larger duplication is being removed.
- Business effect: none directly; useful only as opportunistic cleanup.
- Fix complexity: low
- Recommended strategy: remove the redundant branch when touching the recovery path.

## 5. Architecture Review

### 5.1 What Is Clean

- The project has recognizable layer boundaries: UI, runtime/session orchestration, document pipeline, image pipeline, validation harness.
- Recent extraction of `formatting_transfer.py` and `image_reinsertion.py` from `document.py` is directionally correct.
- `runtime_events.py` and `workflow_state.py` are good examples of simple, explicit contracts.
- `image_pipeline_policy.py` is one of the cleanest modules in the repository because it keeps policy pure.

### 5.2 What Is Weak

- The orchestration layer is too thick. Several files exist mainly to adapt or forward state rather than encapsulate distinct business rules.
- The validation harness has started to duplicate product orchestration instead of staying a consumer of it.
- Image pipeline state is too mutable and too widely shared.
- A few small but real plumbing duplications remain in config/runtime/generation code, which increases drift risk more than their size suggests.
- Some low-value tests protect documents and wiring rather than actual behavior.

### 5.3 SOLID / KISS / YAGNI Assessment

- Single responsibility: mixed. Small files often respect it; large files often do not.
- Open/closed: moderate. Policy modules are extensible; orchestration modules are not.
- Liskov/interface safety: weakened by heavy Protocol use without strong runtime validation.
- Interface segregation: decent in some areas, but `ProcessingService` and `ImageAsset` are over-wide.
- Dependency inversion: present, but sometimes over-applied. A few adapters are genuine seams; others are just indirection.
- KISS: mostly respected in small modules, violated in `ui.py`, `generation.py`, `image_generation.py`, `image_pipeline.py`, `processing_runtime.py`.
- YAGNI: mostly acceptable, except for dead config fields and some validation/tooling duplication.

## 6. File-by-File Review

### 6.1 Application and Runtime Modules

| File | Role | Assessment | Recommendation |
| --- | --- | --- | --- |
| `app.py` | Streamlit entrypoint and UI orchestration | Still owns worker lifecycle, state transitions, fallback sync preparation, and some operational cleanup. Too much orchestration remains in UI layer. | Keep as composition root only; move any remaining runtime decisions out. |
| `app_runtime.py` | Adapter between runtime events and Streamlit state | Very thin forwarding layer. Useful only if the adapter contract is expected to vary. | Either formalize it as the only UI-runtime port or collapse it. |
| `application_flow.py` | Idle/restart/preparation orchestration | Good boundary overall, but sync path duplicates normalization work for legacy docs. | Remove duplicate normalization and keep this as the single preparation boundary. |
| `compare_panel.py` | Compare-all informational UI panel | Small, clear, and isolated. Not a problem by itself. | Keep unless compare-all UX is redesigned, then inline or absorb into `ui.py`. |
| `config.py` | Config/env loading | Explicit and readable, but `get_client()` uses unlocked global singleton state and lazy import caching. | Add lock-protected client initialization; keep the rest of the parsing explicit unless the file grows further. |
| `constants.py` | Shared constants | Clean and appropriately small. | No action needed. |
| `logger.py` | Logging and user-facing error formatting | Clean and cohesive. WSL-safe log rotation is a good pragmatic fix. | No structural change needed. |
| `processing_runtime.py` | Runtime queue, upload normalization, restart, conversion | Large and responsibility-heavy. Central runtime utility module has grown into a mixed subsystem, and it carries at least one duplicated summary contract. | Split by concern over time: upload normalization, runtime event application, background worker helpers, and remove summary/helper duplication opportunistically. |
| `processing_service.py` | Dependency wiring facade for processing | Valuable seam, but too dependency-heavy and partially redundant with Protocols in `document_pipeline.py`. | Reduce constructor width or replace with a narrower dependency bundle. |
| `restart_store.py` | Persisted restart/completed source bytes | Simple and reasonably tested. Real weakness is reliance on external `.run/` durability. | Keep, but treat restartability as best-effort and document its failure modes clearly. |
| `runtime_events.py` | Background event dataclasses | Clean and explicit. One of the healthiest contracts in the project. | No action needed. |
| `state.py` | Streamlit session-state contract | Explicit but wide mutable dict contract. Acceptable for Streamlit, but not elegant. | Keep centralization, but avoid adding more unrelated state keys. |
| `ui.py` | UI rendering helpers and preview widgets | Too large; markdown preview iframe theme sync is brittle and should be isolated. | Split markdown preview, result rendering, and status panels into smaller view modules. |
| `workflow_state.py` | Idle/result state enums | Small and clear. | No action needed. |

### 6.2 Document Pipeline Modules

| File | Role | Assessment | Recommendation |
| --- | --- | --- | --- |
| `document.py` | DOCX extraction and document semantics | Improved after decomposition, but still oversized and still exports shared regex/XML internals. | Continue decomposition by extracting shared OOXML helpers and placeholder contracts. |
| `document_pipeline.py` | Main document processing orchestration | Strong seam, but too many Protocol contracts live here, and some are only implicitly enforced. | Keep orchestration here, but reduce protocol surface and validate collaborator contracts earlier. |
| `formatting_transfer.py` | Paragraph mapping and formatting restoration | Complex for valid domain reasons. Main issue is tight dependency on `document.py` internals. | Extract shared OOXML helpers; keep restoration logic local. |
| `generation.py` | LLM prompting and Markdown-to-DOCX conversion | Large mixed module: prompts, marker contract, retry logic, Pandoc integration, plus duplicated response parsing already present in `image_shared.py`. | Remove parser duplication first, then split prompt/marker contract from Pandoc conversion backend. |
| `image_reinsertion.py` | Replace placeholders with final images | Cohesive and reasonably justified. Dependency on `document.py` internals is the main weakness. | Keep, but move shared XML helpers out of `document.py`. |
| `models.py` | Shared domain data contracts | Mostly solid, except `ImageAsset`, which is overburdened. | Narrow image-state models incrementally without breaking current API. |
| `preparation.py` | Preparation caching and job assembly | Good boundary and pragmatic shared-cache design. Deep-copying cached image state is safe but potentially memory-expensive, and one upload helper is duplicated from runtime code. | Reuse the shared upload helper and profile memory if large documents become a problem. |

### 6.3 Image Pipeline Modules

| File | Role | Assessment | Recommendation |
| --- | --- | --- | --- |
| `image_analysis.py` | Heuristic and VLM-based image analysis | Cohesive enough, though heuristic density is rising. | Split heuristics from VLM request handling only if file continues to grow. |
| `image_generation.py` | Candidate generation across strategies | Too large and mixes safe enhancement, deterministic reconstruction fallback, prompt routing, API handling, and adaptation loops. | Split by strategy: safe, semantic, reconstruction-backed generation. |
| `image_pipeline.py` | End-to-end image orchestration | One of the main complexity hotspots; arbitration and scoring should not live here. | Extract ranking and compare-all selection into pure helpers. |
| `image_pipeline_policy.py` | Validation and delivery policy | Clean, focused, and easy to reason about. | Treat as model for future refactors. |
| `image_prompts.py` | Prompt registry loader | Small and clear. | No action needed. |
| `image_reconstruction.py` | Deterministic reconstruction engine | Large, but relatively cohesive. Complexity is domain-driven rather than accidental. | Split extraction vs rendering only if future feature growth justifies it. |
| `image_shared.py` | Shared image helpers | Useful today, but already a catch-all module. | Avoid adding new responsibilities here; split opportunistically. |
| `image_validation.py` | Post-generation validation | Good boundary, but some scoring semantics overlap with other image modules. | Keep validation local; centralize scoring thresholds and candidate ranking. |

### 6.4 Validation and Tooling Modules

| File | Role | Assessment | Recommendation |
| --- | --- | --- | --- |
| `real_document_validation_profiles.py` | Profile registry and runtime resolution | Mostly good, but carries dead `expected_acceptance_policy` surface. | Remove or enforce that field. |
| `real_document_validation_structural.py` | Structural validation harness | Valuable, but increasingly duplicates runtime orchestration. | Reduce to a thin consumer of shared execution helpers. |
| `real_image_manifest.py` | Real image artifact manifest validator | Small, coherent, and useful. | No structural change needed. |
| `scripts/run_pic1_modes.py` | Developer image-comparison helper | Appears stale and likely broken against current app API. | Remove or repair immediately. |
| `tests/artifacts/real_document_pipeline/run_lietaer_validation.py` | Real-document validation runner | Oversized and effectively a parallel app runtime. Major technical-debt hotspot. | Stop adding logic here; extract shared helpers and shrink the runner. |

### 6.5 Quality and Config Files

| File | Role | Assessment | Recommendation |
| --- | --- | --- | --- |
| `requirements.txt` | Direct Python dependencies | Minimal and reasonable, but not reproducible enough by itself. | Add known-good constraints or version pinning for CI/runtime. |
| `pyproject.toml` | Pytest config only | Too minimal for a repository of this size. | Add lint config or tool references here. |
| `pyrightconfig.json` | Static analysis config | Useful, but permissive (`basic`) and tied to `.venv-win` only. | Keep current contract, but increase strictness for touched modules in CI if possible. |

### 6.6 Test Suite Review

| File | Assessment | Recommendation |
| --- | --- | --- |
| `tests/conftest.py` | Lightweight and useful shared fixtures. | Keep simple; do not let it become a hidden framework. |
| `tests/test_app.py` | High-value UI/runtime integration coverage; large but justified. | Split by user flow if it grows further. |
| `tests/test_application_flow.py` | Good orchestration coverage and caught important normalization paths. | Keep. |
| `tests/test_config.py` | Clear and valuable config validation coverage. | Keep. |
| `tests/test_document.py` | Very valuable, but too large to navigate comfortably. | Split by extraction, headings/lists, placeholders, legacy normalization. |
| `tests/test_document_pipeline.py` | Strong orchestration coverage, but a lot of mocked delegation. | Keep outcome-focused tests; trim repetitive lambda-based wiring cases. |
| `tests/test_format_restoration.py` | High-value domain behavior coverage. | Keep. |
| `tests/test_generation.py` | Valuable, but monolithic. | Split by prompt contract, retries, marker handling, Pandoc conversion. |
| `tests/test_image_analysis.py` | Good heuristic/analysis coverage. | Keep. |
| `tests/test_image_generation.py` | Useful but very large; likely brittle over time. | Split by safe path, semantic path, reconstruction path, retries/budgets. |
| `tests/test_image_integration.py` | High-value integration coverage. | Keep. |
| `tests/test_image_pipeline_compare_helpers.py` | Narrow helper coverage; acceptable. | Keep if it protects real compare-all behavior. |
| `tests/test_image_pipeline_policy.py` | Good pure-policy coverage. | Keep. |
| `tests/test_image_prompts.py` | Small and useful. | Keep. |
| `tests/test_image_reconstruction.py` | Large but justified for algorithmic surface. | Split only if maintenance pain becomes real. |
| `tests/test_image_validation.py` | Valuable behavior checks, though some threshold-based assertions may be brittle. | Keep with careful threshold changes. |
| `tests/test_logger.py` | Useful. | Keep. |
| `tests/test_preparation.py` | Good cache/preparation coverage. | Keep. |
| `tests/test_processing_runtime.py` | High-value runtime contract coverage; already caught a converter fallback edge case. | Keep. |
| `tests/test_processing_service.py` | Mostly thin-wiring and event forwarding. | Trim to crash isolation and meaningful event-contract scenarios. |
| `tests/test_real_document_pipeline_validation.py` | High-value real-doc regression coverage. | Keep. |
| `tests/test_real_document_quality_gate.py` | High-value quality gate coverage. | Keep. |
| `tests/test_real_document_validation_corpus.py` | Valuable corpus/registry protection. | Keep. |
| `tests/test_real_document_validation_profiles.py` | Good registry validation, but currently also protects dead acceptance-policy surface. | Update together with profile cleanup. |
| `tests/test_real_image_manifest.py` | Useful artifact integrity coverage. | Keep. |
| `tests/test_real_image_pipeline.py` | High-value real artifact coverage. | Keep. |
| `tests/test_restart_store.py` | Good focused coverage. | Keep. |
| `tests/test_script_workflow_smoke.py` | Valuable protected-workflow regression coverage. | Keep. |
| `tests/test_spec_image_followup.py` | Low-value archived-doc assertions. | Remove from main regression path or move out of pytest suite. |
| `tests/test_spec_image_level1.py` | Low-value archived-doc assertions. | Remove from main regression path or move out of pytest suite. |
| `tests/test_startup_performance_contract.py` | Valuable protected-contract coverage. | Keep. |
| `tests/test_state.py` | Reasonable state contract coverage. | Keep small and explicit. |
| `tests/test_ui.py` | Large UI contract coverage with some HTML/UI detail sensitivity. | Split by preview, result rendering, status panels. |
| `tests/test_workflow_state.py` | Clear, compact, high-signal. | Keep. |

## 7. Migration Plan

All steps below are intentionally PR-sized and avoid broad refactors.

1. PR-1: remove dead and stale surface
   - Delete or repair `scripts/run_pic1_modes.py`.
   - Remove `expected_acceptance_policy` if it is not going to be enforced now.
   - Move `tests/test_spec_image_level1.py` and `tests/test_spec_image_followup.py` out of the main pytest suite.
  - Add lock-protected initialization for `config.get_client()`.
   - Expected effect: lower confusion and less maintenance noise.

2. PR-2: eliminate duplicate normalization work
   - Refactor `application_flow.prepare_run_context()` sync path to normalize once.
  - Remove duplicated response parsing in `generation.py` in favor of the shared implementation.
  - Remove small duplicated runtime helpers where behavior is already identical.
   - Add focused regression test for single-conversion behavior on legacy `.doc` input.
   - Expected effect: lower latency and cleaner upload contract.

3. PR-3: centralize placeholder contract
   - Extract shared marker/placeholder regexes into a small module.
   - Update `document.py`, `generation.py`, `ui.py`, `image_reinsertion.py`, `formatting_transfer.py` to import it.
   - Expected effect: lower drift risk and easier future syntax changes.

4. PR-4: reduce image orchestration coupling
   - Extract compare-all scoring and candidate ranking from `image_pipeline.py` into a pure helper/policy module.
   - Add focused tests for ranking behavior independent of runtime events.
   - Expected effect: easier image-mode tuning.

5. PR-5: continue document shared-helper extraction
   - Move shared OOXML traversal helpers out of `document.py` into a neutral helper module.
   - Update `formatting_transfer.py` and `image_reinsertion.py` to depend on that helper instead of `document.py` internals.
   - Expected effect: cleaner module boundaries and easier future decomposition.

6. PR-6: trim test noise and split oversized tests
   - Split `tests/test_document.py`, `tests/test_generation.py`, `tests/test_image_generation.py`, `tests/test_ui.py` by concern.
   - Reduce wiring-heavy cases in `tests/test_processing_service.py` and `tests/test_document_pipeline.py` where they do not protect distinct outcomes.
   - Expected effect: faster review and easier failure diagnosis.

7. PR-7: add minimal quality gate
   - Add Ruff with a minimal rule set: unused imports, duplicate imports, obvious simplifications, basic formatting checks.
   - Keep Pyright, but consider stricter checking for changed files only.
   - Expected effect: catch dead code and drift earlier without heavy infrastructure.

## 8. Recommended Post-Change Test Strategy

After any cleanup work, prioritize these verification types:

- Contract tests around upload normalization and restartability.
- Behavioral tests around placeholder preservation and image reinsertion.
- Pure policy tests for image candidate arbitration and validation delivery.
- Real-document validation only after shared orchestration changes.
- UI tests only for user-visible behavior, not archived-doc wording or internal HTML incidental details.

Suggested targeted verification per cleanup wave:

- After PR-1: profile tests, workflow smoke, any script-specific coverage.
- After PR-2: `tests/test_application_flow.py`, `tests/test_processing_runtime.py`, `tests/test_document.py` legacy-doc cases.
- After PR-3: document/generation/ui/image reinsertion tests.
- After PR-4: image pipeline policy and integration tests.
- After PR-5: formatting restoration and reinsertion tests.
- After PR-6: only the split files plus one broader smoke pass.

## 9. Metrics and Target Values

These targets are realistic and do not require overengineering:

- Reduce files over 1000 lines in active application code from 5 to 2 or fewer.
- Reduce direct placeholder-regex definitions from 3+ locations to 1 canonical source.
- Remove 100 percent of dead config fields that are parsed but not enforced.
- Reduce thin-wiring tests in the main suite by at least 50 percent.
- Keep critical runtime/real-document contract tests intact while reducing overall test maintenance cost.
- Add one lint gate that catches unused imports and obvious dead code before merge.

## 10. Machine-Readable Summary

```yaml
reviewed_at: 2026-03-24
scope:
  application_modules: true
  test_suite: true
  tooling_configs: true
  docs_sampled_where_relevant: true
summary:
  overall_assessment: healthy_but_concentrated_complexity
  diagnostics_errors_found: 0
  direct_import_surface:
    - streamlit
    - dotenv
    - openai
    - docx
    - lxml
    - pypandoc
    - PIL
    - pytest
  top_hotspots:
    - tests/artifacts/real_document_pipeline/run_lietaer_validation.py
    - image_generation.py
    - document.py
    - generation.py
    - document_pipeline.py
    - image_reconstruction.py
    - formatting_transfer.py
    - image_pipeline.py
    - processing_runtime.py
    - ui.py
findings:
  - id: ARCH-001
    severity: critical
    path:
      - app.py
      - app_runtime.py
      - processing_runtime.py
      - processing_service.py
      - document_pipeline.py
    category: architecture
    title: Orchestration layering is too thick
    impact: high_change_cost_and_contract_drift
    fix_effort: medium
    business_link: slows_safe_feature_delivery
  - id: STALE-001
    severity: critical
    path:
      - scripts/run_pic1_modes.py
    category: stale_code
    title: Developer script references removed app API
    impact: broken_tooling
    fix_effort: low
    business_link: wastes_debug_time
  - id: PERF-001
    severity: high
    path:
      - application_flow.py
      - processing_runtime.py
      - app.py
    category: optimization
    title: Legacy doc normalization can happen twice in sync preparation path
    impact: avoidable_latency_and_extra_conversion_work
    fix_effort: low
    business_link: slower_restart_and_fallback_flows
  - id: REL-001
    severity: high
    path:
      - config.py
    category: reliability
    title: OpenAI client singleton is initialized without locking
    impact: inconsistent_singleton_behavior_under_concurrency
    fix_effort: low
    business_link: reduces_threaded_runtime_risk
  - id: DUP-002
    severity: high
    path:
      - generation.py
      - image_shared.py
    category: duplication
    title: OpenAI response parsing logic is duplicated across modules
    impact: parser_drift_and_slower_api_shape_updates
    fix_effort: low
    business_link: simplifies_model_api_maintenance
  - id: DATA-001
    severity: high
    path:
      - models.py
    category: architecture
    title: ImageAsset is overloaded with mutable pipeline state
    impact: high_coupling_across_image_modules
    fix_effort: medium
    business_link: harder_to_extend_image_features_safely
  - id: ARCH-002
    severity: high
    path:
      - real_document_validation_structural.py
      - tests/artifacts/real_document_pipeline/run_lietaer_validation.py
    category: duplication
    title: Validation harness partially reimplements runtime orchestration
    impact: validator_runtime_drift
    fix_effort: medium
    business_link: higher_regression_and_maintenance_cost
  - id: MOD-001
    severity: high
    path:
      - image_pipeline.py
      - image_pipeline_policy.py
    category: complexity
    title: Candidate scoring and arbitration live in orchestration layer
    impact: harder_policy_tuning
    fix_effort: medium
    business_link: slower_image_pipeline_iteration
  - id: UI-001
    severity: high
    path:
      - ui.py
      - app.py
    category: ui_architecture
    title: UI rendering module is too large and uses brittle iframe theme sync
    impact: fragile_ui_changes
    fix_effort: medium
    business_link: slower_ux_iteration
  - id: DUP-001
    severity: medium
    path:
      - document.py
      - generation.py
      - ui.py
    category: duplication
    title: Placeholder and marker regex contracts are duplicated
    impact: silent_contract_drift
    fix_effort: low
    business_link: risk_of_broken_placeholder_handling
  - id: MOD-002
    severity: medium
    path:
      - document.py
      - formatting_transfer.py
      - image_reinsertion.py
    category: coupling
    title: Shared OOXML helpers remain trapped in document.py internals
    impact: blocks_further_decomposition
    fix_effort: medium
    business_link: higher_refactor_cost
  - id: DEAD-001
    severity: medium
    path:
      - real_document_validation_profiles.py
    category: dead_code
    title: expected_acceptance_policy is parsed but not enforced
    impact: misleading_config_surface
    fix_effort: low
    business_link: false_confidence_in_validation_policy
  - id: TEST-001
    severity: medium
    path:
      - tests/test_spec_image_level1.py
      - tests/test_spec_image_followup.py
    category: test_quality
    title: Spec-content assertions are low-signal regression tests
    impact: brittle_noise
    fix_effort: low
    business_link: higher_maintenance_with_low_protection
  - id: TEST-002
    severity: medium
    path:
      - tests/test_processing_service.py
    category: test_quality
    title: Several tests are thin wiring checks
    impact: low_signal_test_volume
    fix_effort: low
    business_link: slower_test_maintenance
  - id: OPS-001
    severity: medium
    path:
      - pyproject.toml
      - pyrightconfig.json
    category: tooling
    title: Minimal static quality gate beyond pytest
    impact: dead_code_and_style_drift_survive_longer
    fix_effort: low
    business_link: cleanup_cost_accumulates
  - id: DUP-003
    severity: medium
    path:
      - processing_runtime.py
      - state.py
    category: duplication
    title: Image processing summary defaults are duplicated
    impact: small_but_real_contract_drift_risk
    fix_effort: low
    business_link: reduces_reset_and_ui_counter_maintenance_cost
  - id: DUP-004
    severity: medium
    path:
      - preparation.py
      - processing_runtime.py
    category: duplication
    title: In-memory uploaded file helper is duplicated
    impact: two_edit_points_for_one_helper_contract
    fix_effort: low
    business_link: reduces_small_runtime_maintenance_friction
  - id: APP-002
    severity: low
    path:
      - app.py
    category: maintainability
    title: Main UI flow still carries late imports and repeated frame-finalization calls
    impact: slightly_harder_control_flow_maintenance
    fix_effort: low
    business_link: makes_ui_orchestration_edits_cheaper
  - id: GEN-001
    severity: low
    path:
      - generation.py
    category: dead_code
    title: Recovery path still contains a redundant duplicated raise branch
    impact: minor_control_flow_noise
    fix_effort: low
    business_link: opportunistic_cleanup_when_touching_generation
migration_plan:
  - id: PR-1
    title: Remove stale and dead surface
    depends_on: []
    expected_effect: less_noise_and_less_confusion
  - id: PR-2
    title: Normalize uploads only once
    depends_on: []
    expected_effect: lower_latency_and_cleaner_contract
  - id: PR-2A
    title: Deduplicate response parsing and small runtime helpers
    depends_on: []
    expected_effect: lower_parser_drift_and_smaller_maintenance_surface
  - id: PR-3
    title: Centralize placeholder contract
    depends_on: []
    expected_effect: lower_drift_risk
  - id: PR-4
    title: Extract image candidate ranking logic
    depends_on:
      - PR-3
    expected_effect: easier_policy_changes
  - id: PR-5
    title: Extract shared OOXML helpers from document.py
    depends_on: []
    expected_effect: cleaner_module_boundaries
  - id: PR-6
    title: Split oversized tests and trim thin wiring
    depends_on:
      - PR-1
    expected_effect: better_signal_to_noise
  - id: PR-7
    title: Add minimal lint gate
    depends_on: []
    expected_effect: earlier_detection_of_dead_code_and_drift
targets:
  active_code_files_over_1000_lines: 2
  placeholder_contract_sources: 1
  dead_config_fields: 0
  thin_wiring_tests_reduced_percent: 50
  lint_gate_present: true
```