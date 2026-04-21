# Codebase Refactor Follow-up Spec

Date: 2026-04-20
Status: Active specification in implementation
Scope type: architecture and maintainability follow-up
Primary inputs:

- user-provided review notes dated 2026-04-20
- docs/ARCHIVE_INDEX.md
- docs/archive/specs/ARCHITECTURE_REFACTORING_SPEC_2026-03-25.md
- docs/archive/specs/DOCUMENT_MODULE_DECOMPOSITION_SPEC_2026-03-20.md
- docs/reviews/CODE_REVIEW_REPORT_2026-03-24.md

## 1. Purpose

This specification validates which review remarks are still current in the repository as of 2026-04-20 and defines a safe, staged refactor plan for the remaining architectural debt.

This is a planning document only. It does not authorize broad code movement without an approved implementation slice.

## 2. Constraints

The following repository contracts remain protected during this workstream:

1. The application stays a monolith.
2. The WSL-first runtime and test workflow stay unchanged.
3. The startup performance contract remains protected.
4. Real-document validation must continue to use production-compatible paths.
5. Archive docs remain historical context only; active work belongs in docs/specs/ and related canonical docs.
6. Sub-packages under the current repository root are allowed when they reduce ownership ambiguity; only a repo-wide `src/` layout migration is out of scope for this spec.

## 3. Measurement Methodology

To avoid future review churn, this spec fixes the counting methodology for `st.session_state` references.

Baseline metrics currently referenced by this spec:

1. `matched lines`: unique `file:line` matches for the literal token `st.session_state.` across `*.py` files.
2. `total occurrences`: raw substring occurrences of `st.session_state.` across `*.py` files.
3. The currently cited baseline numbers are `255 matched lines` and `260 total occurrences`, taken from grep-based review measurements (excluding `.venv`, `.run`, `__pycache__`).
4. The earlier draft values `222` and `321` from an earlier review round used inconsistent `--exclude-dir` settings and should not be used as the repo-wide baseline.
5. The even earlier draft value `226` referred to a narrower hotspot slice and should not be used either.

Usage rule for this spec:

1. use `matched lines` as the primary architecture metric when discussing spread;
2. use `total occurrences` as the secondary metric when discussing density inside large hotspot files;
3. whenever a later review cites a count, it must say which metric it uses.
4. before P1 implementation begins, rerun these metrics via a checked-in canonical script or test helper and replace any stale baseline numbers in this document.

## 4. Validation Baseline At Slice Start

The review notes were directionally strong, but several details were already outdated at validation time and needed correction before they could be used as an engineering plan.

This section is a baseline snapshot captured before the implementation slices recorded later in this spec. Live status for the repository after implementation belongs to the dated progress notes and the explicit `P2`/`P3`/`P4` status sections, not to the historical counts below.

### 4.1 Confirmed As Still Relevant

1. `document.py` is still a god-module.
   Current state: 2682 lines and 122 top-level `def`/`class` entries.
   The file still combines extraction, role heuristics, paragraph-boundary normalization, relation normalization, semantic block assembly, AI review, and table rendering.

2. `document_pipeline.py:run_document_processing()` is still the main orchestration hotspot.
   Current state: entry point starts at line 545 with 33 keyword-only parameters and remains a large single function with a wide DI surface and repeated failure-path emission logic.

3. `config.py:load_app_config()` is still oversized.
   Current state: function still starts at line 745 inside a 1589-line module and still performs largely flat section-by-section parsing.

4. `app.py` still mixes UI rendering, orchestration, and session mutation.
   Current state: `main()` starts at line 516 in an 848-line file; `_maybe_apply_file_recommendations()` starts at line 373 and still owns a dense block of session-backed recommendation logic.

5. `processing_runtime.py` still breaches the intended session-state ownership boundary.
   Current state: direct `st.session_state` mutations remain in worker/runtime helpers, including processing start/stop and restart persistence paths.

6. Direct `st.session_state` usage is still a real architecture issue.
   Current state: grep-based review measurements currently place the repo-wide baseline at 255 matched lines and 260 raw occurrences of `st.session_state.` (excluding `.venv`, `.run`, `__pycache__`). The densest hotspots remain `state.py`, `app.py`, `processing_runtime.py`, and `ui.py`. These baseline numbers must be re-run by a canonical checked-in counter before P1 starts.

7. `tests/test_document.py` is still oversized.
   Current state: 3017 lines.

8. `tests/artifacts/real_document_pipeline/run_lietaer_validation.py` is still oversized for a test-side helper.
   Current state: 2038 lines.

9. Transitional compatibility surface still exists.
   Current state: `README.md` still explicitly says `normalize_semantic_output_docx()` remains a compatibility no-op.

10. Hygiene issues still exist.
   Current state on validation start: `search_result.txt`, `wsl_out.txt`, and `.pyright_errors.txt` were present in the repository root and polluted review output. This slice removes them from the worktree and adds root-level ignore rules to keep them out.

11. Root-level review report placement is still inconsistent with the docs contract.
   Current state: `CODE_REVIEW_REPORT.md` exists in the repository root while an archived copy also exists under `docs/archive/reviews/`.

### 4.2 Partially Relevant, But Needing Correction

1. Flat root-level layout is still suboptimal, but the exact recommended package split must account for the work already completed in March-April.
   Important correction: earlier decomposition already moved formatting and reinsertion concerns out of `document.py`, so the new plan should not pretend the repo is still at the pre-decomposition baseline.

2. `config.py:33 OpenAI = None` is still stylistically weak, but the concurrency bug from the older review is no longer current.
   Current state: `_CLIENT_LOCK = Lock()` and double-checked client initialization now exist.
   Conclusion: keep as low-severity cleanup, not as a correctness or thread-safety issue.

3. Session-state sprawl is still real, but the distribution is narrower than described.
   Correction: the current repo does not support the claim of "222 direct refs across 10+ modules". The currently cited baseline is 255 matched lines and 260 raw occurrences repo-wide (excluding `.venv`, `.run`, `__pycache__`), concentrated in 4 main modules rather than spread broadly across 10+ files. Those exact counts are methodological baselines, not immutable constants, and must be re-run by the canonical counter before P1 starts.

4. The image domain still deserves a clearer ownership boundary, but the count is no longer "12 image_*.py files".
   Current state: 10 root-level image modules were confirmed: `image_analysis.py`, `image_generation.py`, `image_output_policy.py`, `image_pipeline.py`, `image_pipeline_policy.py`, `image_prompts.py`, `image_reconstruction.py`, `image_reinsertion.py`, `image_shared.py`, and `image_validation.py`.

### 4.3 No Longer Current Or Already Addressed

1. Old response-parsing duplication between `generation.py` and `image_shared.py` is no longer a primary problem.
   Current state: `generation.py` imports `call_responses_create_with_retry` from `image_shared.py`; the previous duplicate parsing helpers are no longer present in the same form.

2. The old high-severity remark about missing client locking in `config.py` is obsolete.
   Current state: `_CLIENT_LOCK` is present and used inside `get_client()`.

3. The stray file `.join(c))PY` was not found and should not appear in the new plan.

## 5. Additional Current-State Findings

The fresh validation surfaced several details that the new implementation plan must treat explicitly.

### 5.1 `document.py` Still Performs Legacy Double Normalization Fallback

`document.py:_read_uploaded_docx_bytes()` still calls `normalize_uploaded_document()` for non-zip uploads, even though the authoritative normalization boundary is documented as living earlier in the runtime flow.

This keeps the old "potential double normalization" concern alive and makes it a valid candidate for a narrow correctness and ownership cleanup.

### 5.2 `app.py` Has Grown Since The Archived Architecture Wave

The archived architecture spec recorded a much smaller direct session-write footprint in `app.py`. The current file is larger and now contains additional recommendation-state ownership, including direct writes such as `text_transform_assessment` and multiple recommendation-related keys.

This means the next refactor wave should treat `app.py` as an active hotspot again rather than assuming earlier cleanup fully stabilized it.

### 5.3 `state.py` Is Not Yet A Full Session Facade

`state.py` clearly owns many write helpers and defaults, but it still directly exposes raw `st.session_state` operations instead of a narrow typed store abstraction. The repo therefore has centralization, but not full encapsulation.

### 5.4 March Decomposition Delta Is Material And Must Not Be Re-litigated

The already-completed March wave moved two major domains out of `document.py`:

1. formatting restoration into `formatting_transfer.py`;
2. image reinsertion into `image_reinsertion.py`.

The follow-up decomposition work therefore applies only to the still-unextracted document subdomains:

1. paragraph role heuristics;
2. paragraph-boundary normalization;
3. paragraph-boundary AI review;
4. relation normalization;
5. semantic block assembly;
6. table rendering and related light document-domain helpers.

### 5.5 The First P1a Key Family Was Internally Split By Lifecycle Phase

Fresh implementation audit confirmed that the first `P1a` key family was not merely spread across modules in the abstract; it was split by lifecycle phase inside the exact keys selected for first migration.

Current pre-P1a shape:

1. processing-start writes lived in `processing_runtime.py`;
2. reset and completion writes lived in `state.py`;
3. `selected_source_token` writes also lived in `application_flow.py` during file-selection sync;
4. some read-side access still lived in `app.py` as raw composition-edge reads.

This matters because the first migration slice must establish one authoritative write owner for the first key family rather than merely reducing raw-reference counts.

## 5A. Implementation Status

This section tracks implementation progress for the approved first slice only.

### 5A.1 P0 Status

1. `P0.1` Root diagnostic artifacts ignore/cleanup status: implemented in this slice.
2. `P0.2` Active review report move into `docs/reviews/`: implemented in this slice.
3. `P0.3` `_read_uploaded_docx_bytes()` double-normalization fallback removal: implemented in this slice.
4. `P0.4` Compatibility-surface sunset note in `README.md` and exported entrypoints: implemented in this slice.

### 5A.2 P1a Status

1. `P1a.1` checked-in ownership matrix artifact: implemented in this slice.
2. `P1a.2` initial whitelist-backed enforcement test: implemented in this slice.
3. `P1a.3` first migrated lifecycle/source-identity key family: implemented for the processing-start transition, stop-request path, `selected_source_token` write ownership, and read-side helpers in this slice.
4. `P1a.4` recommendation-state migration: not started by design; deferred to `P1b`.

### 5A.3 P1b Status

1. `P1b.1` recommendation-state write ownership centralization in `state.py`: implemented for `text_transform_assessment`, recommendation-state session keys, and pending widget-state application in this slice.
2. `P1b.2` `application_flow.py:selected_source_token` write-side ownership gap: implemented in this slice.

### 5A.4 P2 Status

1. `P2.1` dependency, emitter, context, and processing-state containers for `run_document_processing()`: implemented in this slice.
2. `P2.2` phase-oriented helper split for initialization, block processing, image processing, placeholder validation, DOCX build, and success finalization: implemented in this slice.
3. `P2.3` public `run_document_processing()` entrypoint reduction: advanced in the SLO follow-up slice; component wiring and run execution now live behind dedicated helpers so the public entrypoint is a thin facade over builder-plus-executor orchestration.
4. `P2.4` repeated failure-path emission cleanup: advanced in this slice through shared terminal-result helpers plus dedicated block-phase failure handlers for invalid-job, generation-failure, processed-output rejection, and marker-registry failure paths.
5. `P2.5` block-phase happy-path extraction: implemented in this slice through dedicated helpers for block start emission, block execution, marker-registry append, and block completion emission.
6. `P2.6` single-block orchestration extraction: implemented in this slice through `_process_single_block()`, leaving `_run_block_processing_phase()` as a thin loop over stop-check plus per-block dispatch.

### 5A.5 P3 Status

1. `P3.1` first paragraph-role extraction into `document_roles.py`: implemented in this slice while keeping `document.py` as the compatibility import surface for existing callers and tests.
2. `P3.2` relation-normalization extraction into `document_relations.py`: implemented in this slice while keeping `document.py` as the compatibility import surface for existing callers, tests, and report-writer monkeypatches.
3. `P3.3` semantic-block assembly extraction into `document_semantic_blocks.py`: implemented in this slice while keeping `document.py` as the compatibility import surface for existing callers and preserving the legacy relation-settings wrapper used by the document facade.
4. `P3.4` deterministic paragraph-boundary normalization extraction into `document_boundaries.py`: implemented in this slice while keeping `document.py` as the compatibility facade for normalization entry points, settings wrappers, and report-artifact monkeypatch targets.
5. `P3.5` boundary AI review extraction into `document_boundary_review.py`: implemented in this slice while keeping `document.py` as the compatibility facade for settings resolution, execution entry points, and monkeypatch-friendly wrappers used by existing tests.
6. `P3.6` table rendering extraction into `document_tables.py`: implemented in this slice while keeping `document.py` as the compatibility facade for raw-table construction and HTML rendering helpers.
7. `P3.7` shared XML ownership cleanup into `document_shared_xml.py`: implemented in this slice for source XML fingerprinting, drawing/image XML forensics, and numbering XML helpers, while `document.py` keeps compatibility wrappers for existing callers.
8. `P3.8` remaining DOCX extraction, archive-validation, list-metadata, and inline render ownership move into `document_extraction.py`: implemented in the SLO follow-up slice, with `document.py` reduced to a compact compatibility facade that preserves legacy monkeypatch/test seams while the heavy extraction logic now lives outside the facade.

### 5A.6 P4 Status

1. `P4.1` first section-loader extraction for document-structure settings inside `config.py:load_app_config()`: implemented in this slice for paragraph-boundary normalization, paragraph-boundary AI review, relation normalization, structure recognition, and structure validation.
2. `P4.2` image/semantic-validation and image-output section-loader extraction inside `config.py:load_app_config()`: implemented in this slice while keeping model-registry migration logic untouched.
3. `P4.3` text runtime defaults and output-font section-loader extraction inside `config.py:load_app_config()`: implemented in this slice while preserving env precedence and validation rules.
4. `P4.4` model-registry resolution and legacy-warning emission extraction inside `config.py:load_app_config()`: implemented in this slice while preserving canonical-over-legacy precedence and warning behavior.
5. `P4.5` `AppConfig` assembly/body-size SLO follow-up: implemented in this slice by moving clamp normalization into section helpers and routing final object assembly through a dedicated `_build_app_config()` helper.
6. residual `P4` cleanup and any optional further reduction after helper extraction: not started by design.

## 6. Refactor Goals

This follow-up wave should aim for the following outcomes:

1. Reduce ownership ambiguity across `app.py`, `processing_runtime.py`, and `state.py`.
2. Make document processing orchestration readable and phase-oriented without changing product behavior.
3. Shrink the cognitive surface of `document.py` by extracting coherent subdomains behind compatibility exports.
4. Make configuration loading section-oriented rather than a long flat parse routine.
5. Clean up repository hygiene and docs placement drift so future reviews do not keep rediscovering the same noise.

## 7. Definition Of Done And Size SLOs

The following target sizes are not style preferences; they are the closure criteria for the main refactor slices unless a later approved note explicitly overrides them.

1. `document.py` compatibility facade: target `<= 300` lines after P3.
2. `load_app_config()` top-level body: target `<= 150` lines after P4.
3. `run_document_processing()` entrypoint body: target `<= 80` lines after P2, excluding small dataclass definitions and tiny wrappers.
4. Max production file size target: `<= 1000` lines after the relevant phase, except for `models.py` and any future config-schema file explicitly approved as an exception.

## 8. Non-Goals

This spec does not authorize the following:

1. a repo-wide package migration from root modules into `src/` in one step;
2. replacement of Streamlit or the worker model;
3. speculative framework adoption for config or state without a narrow migration slice;
4. moving archived historical docs back into active locations;
5. broad renaming-only churn that does not reduce ownership ambiguity.

## 9. Deferred And Explicitly Out Of Scope For This Wave

The following hotspots are recognized but are not first-wave implementation targets under this spec unless they become direct dependencies of an approved slice.

1. `generation.py` is a real hotspot and should be treated as deferred, not ignored.
   Reason: prompt/retry behavior is high-risk and can be refactored after runtime/session and pipeline ownership are clearer.

2. `image_generation.py` and `image_pipeline.py` are deferred as a dedicated image-domain phase, not denied as debt.
   Reason: the image domain needs its own ownership plan rather than being half-absorbed into the document/runtime slices.

3. `formatting_transfer.py` is deferred but explicitly recognized as a DOCX-correctness-sensitive module.
   Reason: it should be reviewed after the document-facade cleanup clarifies what shared XML helpers still belong in the document domain.

4. `models.py` is intentionally out of scope for structural breakup in this wave.
   Reason: it is currently a stable single source of truth; changing it now would add churn without reducing the primary ownership hotspots.

5. `tests/test_document_pipeline.py` and `tests/test_app.py` are acknowledged as future split candidates alongside `tests/test_document.py`.
   Reason: test decomposition should follow production boundaries and not front-run them.

## 10. Proposed Refactor Plan

The plan is intentionally staged to keep risk proportional to the architectural value of each slice.

### P0. Baseline Cleanup And Contract Tightening

Objective: remove misleading noise and lock the boundaries that keep contaminating later work.

Tasks:

1. Remove or ignore-root diagnostic artifacts from version control (`search_result.txt`, `wsl_out.txt`, `.pyright_errors.txt`) and update `.gitignore` if needed.
2. Move the maintained 2026-03-24 root review report into `docs/reviews/` as the active review copy, using a date-stable name such as `CODE_REVIEW_REPORT_2026-03-24.md`, and stop treating deletion as the default path.
3. Narrow `document.py:_read_uploaded_docx_bytes()` so already-normalized runtime paths are not forced through a legacy fallback normalizer.
4. Write explicit deprecation intent for the compatibility surface with sunset criteria:
   - `normalize_semantic_output_docx()` must be either removed or reduced to an internal alias no later than the end of P3 or 2026-06-30, whichever comes first, once production, validation, and test call sites are migrated;
   - `preserve_source_paragraph_properties()` remains the canonical public formatting entrypoint for this wave and is not a removal target until a later formatting-transfer-specific spec supersedes it.
5. Record the compatibility-surface deprecation note in two concrete locations during P0:
   - the compatibility note in `README.md`;
   - docstrings or nearby comments on the exported compatibility entrypoints themselves, so the sunset rule is visible at the call site.
6. Update this specification in the same slice when implementation uncovers a narrower ownership fracture than the planning draft had stated.

Acceptance criteria:

1. Root noise files no longer pollute repository review output.
2. Docs placement matches the docs contract.
3. Upload normalization ownership is documented and not ambiguously reintroduced by helper code.
4. The compatibility-surface sunset criteria are written in code-facing docs rather than implied.

Regression gates:

1. `tests/test_config.py` for docs/config-adjacent cleanup that touches load-time behavior.
2. `tests/test_document.py` selectors covering upload normalization helpers if `_read_uploaded_docx_bytes()` changes.

Rollback rule:

1. P0 ships as one revertable slice and must not be mixed with P1 API movement.

### P1. Session-State Ownership Slice

Objective: turn the current partial centralization into an actual ownership contract.

Tasks:

1. Define a `SessionStore` or equivalent typed facade in `state.py` for the keys actively shared across `app.py`, `processing_runtime.py`, and `ui.py`.
2. Move direct write paths out of `processing_runtime.py` where the same mutation can be expressed through `state.py` APIs.
3. Move recommendation-state mutation helpers out of `app.py` into `state.py` or a narrowly-scoped state-oriented module.
4. Establish a rule: outside `state.py` and very small Streamlit composition edges, raw `st.session_state` access is legacy-only.
5. Produce a mandatory session-state ownership matrix before broad migration starts.

Implementation sequencing:

1. `P1a` is the required first implementation unit.
2. `P1a` must ship the ownership matrix, the initial enforcement test, and the first migrated key family before any recommendation-state migration begins.
3. `P1b` may migrate recommendation-state keys only after `P1a` is merged and stable.

First migrated key family for `P1a`:

1. processing lifecycle keys: `processing_outcome`, `processing_worker`, `processing_event_queue`, `processing_stop_event`, `processing_stop_requested`.
2. source-identity keys coupled to the processing lifecycle: `latest_source_name`, `latest_source_token`, `selected_source_token`, `latest_image_mode`.
3. Recommendation-state keys are explicitly deferred to `P1b` rather than mixed into the first PR.

Initial whitelist rule:

1. `state.py` is the long-term owner for the migrated keys listed above.
2. `app.py` may retain temporary raw reads only at Streamlit composition edges that are explicitly listed in the whitelist artifact.
3. `processing_runtime.py` is not allowed to keep ad hoc writes for any `P1a` key once the slice lands.

Mandatory deliverable:

1. Add a checked-in ownership inventory mapping `key -> owner module -> writer callers -> reader callers -> migration phase`.
2. The inventory may live in `docs/architecture/` or another approved canonical location, but it must be versioned and updated during P1.
   Current slice artifact: `docs/architecture/session_state_ownership_matrix_2026-04-20.md`.

Enforcement mechanism:

1. Preferred mechanism: an AST-based regression test that fails when raw `st.session_state.` attribute access appears outside an explicit whitelist.
2. Minimum acceptable fallback: a grep-based test with an explicit whitelist file.
3. The whitelist must distinguish between long-term owners and temporary legacy exceptions so the allowed surface shrinks over time.

Implementation rule:

1. Do not try to eliminate every read and write in one pass.
2. Start with the `P1a` lifecycle and source-identity keys listed above.
3. Add the ownership-matrix artifact and the boundary-enforcement test before continuing the migration.
4. Treat recommendation-state migration as a separate `P1b` unit after the lifecycle keys are stable.

Acceptance criteria:

1. `processing_runtime.py` no longer owns ad hoc session mutation logic for core lifecycle state.
2. `app.py` sheds recommendation-state bookkeeping that is not fundamentally UI composition.
3. New session keys are introduced through a documented owner.
4. The enforcement test fails on non-whitelisted raw access.

Regression gates:

1. `tests/test_state.py`
2. `tests/test_processing_runtime.py`
3. `tests/test_app.py`
4. one visible real-document rerun via `Run Real Document Validation Profile` before closing the whole P1 slice if shared runtime lifecycle behavior changed

Rollback rule:

1. Ship P1 in small revertable units, but keep the ownership matrix and enforcement test in the first commit of the phase.

### P2. `run_document_processing()` Phase Decomposition

Objective: replace the current god-function with explicit phase boundaries while preserving the existing DI-friendly testability.

Tasks:

1. Introduce a single dependency container for orchestration collaborators instead of a 25+ parameter top-level function signature.
2. Split execution into explicit internal phases:
   - initialization and validation
   - block loop / markdown generation
   - image processing
   - docx assembly and formatting
   - finalization and failure handling
3. Introduce a small processing state object carrying accumulated markdown, registry data, timing, and terminal outcome.
4. Consolidate repeated failure emission patterns into one or two explicit helpers.

Boundary decision for this phase:

1. `app_config` remains the canonical parameter bag during P2 for already-grouped run inputs such as `processing_operation`, `source_language`, and `target_language`.
2. The first P2 decomposition must not thread newly typed per-run settings through every intermediate helper signature if the same value already travels inside `app_config`.
3. `ProcessingContext` may expose typed mirrors for readability, but those mirrors are derived from the existing runtime inputs and do not create a second source of truth during the first decomposition pass.
4. Any later move away from `app_config` as the canonical bag requires its own approved follow-up slice rather than being folded implicitly into P2.

Type sketch:

```python
@dataclass(frozen=True)
class ProcessingDependencies:
   get_client: ClientFactory
   ensure_pandoc_available: Callable[[], None]
   load_system_prompt: SystemPromptLoader
   generate_markdown_block: MarkdownGenerator
   process_document_images: ImageProcessor
   inspect_placeholder_integrity: PlaceholderInspector
   convert_markdown_to_docx_bytes: MarkdownToDocxConverter
   preserve_source_paragraph_properties: ParagraphPropertiesPreserver
   normalize_semantic_output_docx: SemanticDocxNormalizer
   reinsert_inline_images: ImageReinserter
   log_event: EventLogger
   present_error: ErrorPresenter
   resolve_uploaded_filename: FilenameResolver
   should_stop_processing: StopPredicate


@dataclass(frozen=True)
class ProcessingEmitters:
   emit_state: StateEmitter
   emit_finalize: FinalizeEmitter
   emit_activity: ActivityEmitter
   emit_log: LogEmitter
   emit_status: StatusEmitter


@dataclass(frozen=True)
class ProcessingContext:
   uploaded_file: object
   jobs: ProcessingJobs
   source_paragraphs: Sequence[ParagraphLike] | None
   image_assets: Sequence[ImageAssetLike]
   image_mode: str
   app_config: Mapping[str, object]
   model: str
   max_retries: int
   processing_operation: str
   source_language: str
   target_language: str
   runtime: object


@dataclass
class ProcessingState:
   processed_chunks: list[str]
   generated_paragraph_registry: list[dict[str, object]]
   system_prompt: str | None
   started_at: float
```

Naming is illustrative, but the three-way split between dependencies, emitters, and runtime context is mandatory to avoid bike-shedding the container boundary during implementation.

Acceptance criteria:

1. No single orchestration method should dominate the entire pipeline flow.
2. Failure behavior remains identical from the UI perspective.
3. Existing tests for stop/error paths remain green with only targeted updates.
4. The public entrypoint body is reduced to the P2 SLO rather than merely split into helpers of arbitrary size.

Regression gates:

1. `tests/test_document_pipeline.py`
2. `tests/test_app.py` selectors that cover user-visible error and stop behavior
3. visible rerun of `Run Real Document Validation Profile` using the canonical Lietaer validation target before phase closure

Rollback rule:

1. Keep one revertable commit or tight commit series per phase boundary so the old orchestration path can be restored without also reverting P1/P3 work.

### P3. `document.py` Decomposition Follow-up

Objective: continue the document-module cleanup from the already-completed March decomposition without repeating that earlier work.

Completed baseline from the March wave:

1. formatting restoration moved to `formatting_transfer.py`;
2. image reinsertion moved to `image_reinsertion.py`.

Still in scope for this follow-up wave:

1. paragraph role heuristics;
2. paragraph-boundary normalization;
3. paragraph-boundary AI review;
4. relation normalization;
5. semantic block assembly;
6. table rendering.

Tasks:

1. Extract paragraph role heuristics into a dedicated module.
2. Extract paragraph-boundary normalization and AI review into dedicated modules.
3. Extract relation normalization and semantic block assembly into dedicated modules.
4. Keep `document.py` as a compatibility export surface until downstream imports are migrated.

Recommended target shape:

1. `document.py` remains a compatibility facade.
2. New modules hold the real implementations for roles, boundaries, relations, semantic blocks, and table rendering.
3. Shared XML helpers should live in an explicitly named shared module if they are consumed across multiple document-domain files.

Implementation map for the first P3 planning pass:

1. `document_roles.py` for paragraph role heuristics.
2. `document_boundaries.py` for paragraph-boundary normalization.
3. `document_boundary_review.py` for paragraph-boundary AI review.
4. `document_relations.py` for relation normalization.
5. `document_semantic_blocks.py` for semantic block assembly.
6. `document_tables.py` for table rendering.
7. `document_shared_xml.py` for any XML helpers used across more than one extracted module.

Module-boundary rule:

1. New extraction PRs must target the module map above unless a later approved note intentionally revises it.
2. `document.py` may re-export compatibility names, but extracted modules must not depend back on unrelated private helpers left behind in the facade.
3. Shared helpers discovered during extraction should move into `document_shared_xml.py` rather than creating new cross-imports between sibling extracted modules.

Important caution:

This slice should be implemented only after the `run_document_processing()` ownership cleanup. Otherwise the refactor will multiply moving parts and test churn at the same time.

Acceptance criteria:

1. `document.py` becomes materially smaller.
2. `formatting_transfer.py` and other consumers do not depend on private helpers from a giant facade module without an explicit contract.
3. `tests/test_document.py` can be split by responsibility afterward instead of remaining one catch-all file.
4. `document.py` is reduced to the facade SLO rather than just partially trimmed.

Regression gates:

1. `tests/test_document.py`
2. `tests/test_document_pipeline.py`
3. `tests/test_format_restoration.py`
4. visible rerun of `Run Real Document Validation Profile` before phase closure

Rollback rule:

1. Each extracted subdomain ships as a separate revertable slice; do not bundle all six extractions into one irreducible change.

### P4. Config Loader Refactor

Objective: reduce the maintenance cost of `load_app_config()` without destabilizing runtime behavior.

Tasks:

1. Extract per-section loader helpers with a consistent contract.
2. Keep existing precedence rules intact: config file, env overrides, defaults, and legacy migration warnings.
3. Defer any framework decision (`pydantic`, `attrs`, pure dataclass loaders) until after a narrow section-loader extraction proves the shape.

Decision rule:

1. Do not start with a library migration.
2. First split by section using the existing parsing helpers and tests.
3. Only adopt a declarative schema tool if the remaining boilerplate still justifies it.

Acceptance criteria:

1. `load_app_config()` no longer reads as one flat parse tape.
2. Legacy alias handling remains covered by tests.
3. No runtime config precedence regressions are introduced.
4. The top-level loader meets the P4 size SLO.

Regression gates:

1. `tests/test_config.py`
2. `tests/test_app.py` selectors that cover config-load behavior where applicable

Rollback rule:

1. Keep each section-loader extraction revertable by section family; do not mix config refactor with runtime/session migration.

### P5. Test And Validation Surface Cleanup

Objective: align tests with the new module boundaries once production ownership is cleaner.

Tasks:

1. Split `tests/test_document.py` by responsibility after the `document.py` decomposition boundary exists.
2. Split or otherwise restructure `tests/test_document_pipeline.py` and `tests/test_app.py` once the corresponding production boundaries stabilize.
3. Decide whether `tests/artifacts/real_document_pipeline/run_lietaer_validation.py` should remain a test-side harness, move into a dedicated validation utilities location, or be wrapped by a smaller maintained entrypoint.
4. Keep real-document validation behavior stable while reducing the size of individual helper files.

Regression gates:

1. targeted file-level pytest tasks for each split file
2. visible rerun of `Run Real Document Validation Profile` if the validation harness or reporting path changes

## 11. Recommended Implementation Order

1. P0 baseline cleanup and docs/hygiene correction.
2. P1 session-state ownership slice.
3. P2 pipeline phase decomposition.
4. P3 `document.py` decomposition follow-up.
5. P4 config loader refactor.
6. P5 test and harness cleanup.

This order is intentional:

1. session ownership affects almost every user-facing run;
2. pipeline decomposition reduces the blast radius before deeper document extraction changes;
3. config refactor is valuable but less urgent than runtime and pipeline ownership;
4. test splitting should follow production boundaries, not precede them.

## 12. Review Verdict Summary

The user-provided review is broadly correct on the main architectural debt: oversized document processing modules, oversized config loading, and incomplete session-state encapsulation remain the highest-value refactor targets.

However, the review should not be used verbatim as an implementation brief because several concrete facts are outdated:

1. image-module count changed;
2. session-state spread is narrower than stated;
3. some previously severe findings are already fixed;
4. the repository already completed one document decomposition wave, so the next plan must build on that baseline rather than restart from the older architecture description.

## 13. Approval Gate For Implementation

No large-scale refactor should begin until a concrete implementation slice is chosen from this spec.

Recommended first approved slice:

1. P0 baseline cleanup plus `P1a` session-state ownership tightening.

Concrete contents of that first slice:

1. P0 cleanup items and compatibility-surface documentation notes.
2. The checked-in ownership matrix artifact.
3. The initial whitelist-backed enforcement test.
4. Migration of the `P1a` lifecycle and source-identity keys only.

That slice has the best ratio of architectural value to migration risk and will clarify the remaining work before deeper module movement begins.

## 14. Slice Progress Notes

This section is updated during implementation of the first approved slice.

### 2026-04-20 Additional Progress

1. Started `P5.1` test-surface cleanup with the first low-risk split of `tests/test_document.py`.
2. Moved semantic-block, relation-normalization, and marker-wrapping tests into `tests/test_document_structure_blocks.py` while keeping the remaining facade, extraction, formatting, and reinsertion coverage in `tests/test_document.py`.
3. Kept the split intentionally narrow so production boundary work remains stable and pytest collection/import behavior stays easy to verify.
4. Continued `P5.1` by moving image-reinsertion and delivery-payload coverage into `tests/test_image_reinsertion.py`, leaving `tests/test_document.py` focused on facade, extraction, archive-validation, and formatting-adjacent behavior.
5. Continued `P5.1` again by moving DOCX archive-validation and upload-byte guard coverage into `tests/test_document_extraction.py`, further narrowing `tests/test_document.py` toward formatting and compatibility behavior only.
6. Finished this `tests/test_document.py` decomposition wave by moving the remaining formatting, diagnostics-retention, and compatibility-formatting coverage into `tests/test_format_restoration.py` and deleting the empty catch-all file.
7. Continued `P5.1` beyond the old document catch-all by splitting failure-path and validation-path coverage out of `tests/test_document_pipeline.py` into `tests/test_document_pipeline_failures.py`, leaving the original pipeline test file focused on happy-path, logging, marker, and end-to-end behavior.
8. Continued `P5.1` inside the remaining pipeline surface by moving output-validation and heading-only acceptance coverage into `tests/test_document_pipeline_output_validation.py`, leaving `tests/test_document_pipeline.py` focused on happy-path, logging, marker, stop, and end-to-end behavior.
9. Continued `P5.1` into the app-side test surface by moving recommendation auto-apply and notice-helper coverage out of `tests/test_app.py` into `tests/test_app_recommendations.py`, leaving `tests/test_app.py` focused on main-flow integration, preparation/runtime controls, restartable-state behavior, and compare-panel coverage.
10. Finished the recommendation-domain app split by moving the remaining recommendation integration coverage for summary notice rendering and pending widget-state application out of `tests/test_app.py` into `tests/test_app_recommendations.py`, leaving the main app test file focused on non-recommendation runtime and UI flows.
11. Continued `P5.1` across two more small seams at once: moved restartable-outcome notice and oversized-upload guard coverage out of `tests/test_app.py` into `tests/test_app_restartable_state.py`, leaving the main app test file focused on broader non-restartable composition and runtime flows.
12. Finished the remaining compare-panel extraction from the app catch-all by moving compare-all panel visibility/no-op coverage into `tests/test_compare_panel.py` and relocating flow-specific restartable helper coverage into `tests/test_application_flow.py`, so the leftover `tests/test_app.py` is no longer the home for module-specific helper behavior.

### 2026-04-20 Progress

1. Confirmed and recorded an additional `P1a`-specific problem: the first migrated key family was split by lifecycle phase across `processing_runtime.py`, `state.py`, and `application_flow.py` rather than having one authoritative write owner.
2. Moved the processing-start transition for the first `P1a` key family behind `state.apply_processing_start()` and routed stop requests through `state.request_processing_stop()`.
3. Removed the legacy fallback normalizer from `document.py:_read_uploaded_docx_bytes()` so the runtime normalization boundary remains singular.
4. Added `docs/architecture/session_state_ownership_matrix_2026-04-20.md` and `tests/test_session_state_ownership.py` as the initial ownership artifact plus whitelist-backed regression gate.
5. Moved the maintained review report into `docs/reviews/CODE_REVIEW_REPORT_2026-03-24.md` and ignored root diagnostic artifacts in `.gitignore`.
6. Decomposed `document_pipeline.py:run_document_processing()` into typed containers plus explicit internal phases while preserving the existing public function signature and targeted pipeline behavior.
7. Added shared terminal-result helpers in `document_pipeline.py` so repeated finalize/activity/log emission for failed and stopped paths no longer has to be open-coded at each phase boundary.
8. Extracted the main happy-path portions of block execution in `document_pipeline.py` so `_run_block_processing_phase()` now delegates both the main success flow and the major failure branches to focused helpers.
9. Added `_process_single_block()` so the block-phase loop now mostly expresses orchestration structure rather than inline block lifecycle details.
10. Extracted the first document-structure section loaders from `config.py:load_app_config()` into focused helper functions, keeping model-registry migration logic and the public config API unchanged while reducing flat parse-tape density for the P4 wave.
11. Extracted the image/semantic-validation runtime settings and `image_output` parsing from `config.py:load_app_config()` into dedicated helper functions, further shrinking the remaining flat config-loader body without changing clamps, env precedence, or return shape.
12. Extracted text runtime defaults and `output.fonts` parsing from `config.py:load_app_config()` into dedicated helper functions, preserving context validation, env overrides, and the existing `AppConfig` return contract.
13. Extracted model-registry resolution, legacy fallback precedence, and legacy-warning emission from `config.py:load_app_config()` into a dedicated helper, leaving the top-level loader mostly as section orchestration plus final `AppConfig` assembly.
14. Closed the immediate top-level P2/P4 SLO gaps by routing `run_document_processing()` through dedicated run-component/executor helpers and by moving `load_app_config()` clamp-heavy final assembly into section helpers plus `_build_app_config()`.
15. Started `P3` with the first paragraph-role extraction: role heuristics, heading/caption/list classification helpers, and standalone-heading/caption reclassification now live in `document_roles.py`, while `document.py` remains the compatibility facade for existing imports.
16. Continued `P3` with relation-normalization extraction: `build_paragraph_relations()`, relation-side-effect application, TOC/epigraph relation heuristics, and relation report artifact writing now live in `document_relations.py`, while `document.py` keeps compatibility wrappers for existing imports and test monkeypatch targets.
17. Continued `P3` with semantic-block extraction: block clustering, context excerpt assembly, marker-wrapped block rendering, and editing-job construction now live in `document_semantic_blocks.py`, while `document.py` keeps compatibility re-exports and a facade-level relation-settings wrapper for unchanged call sites.
18. Continued `P3` with deterministic boundary extraction: normalization settings resolution, boundary decision heuristics, merged-raw-paragraph assembly, metrics summarization, and boundary report artifact writing now live in `document_boundaries.py`, while `document.py` keeps facade-level wrappers for orchestration and existing test monkeypatch points.
19. Continued `P3` with boundary AI review extraction: candidate building, request payload construction, recommendation parsing, decision recording, and review artifact writing now live in `document_boundary_review.py`, while `document.py` keeps facade-level wrappers and test monkeypatch seams.
20. Continued `P3` with table rendering extraction: raw-table construction plus HTML table/cell/row rendering now live in `document_tables.py`, while `document.py` keeps compatibility wrappers and continues supplying paragraph text rendering for cell content.
21. Continued `P3` with shared XML ownership cleanup: source XML fingerprinting, drawing/image extraction forensics, and list-numbering XML resolution now live in `document_shared_xml.py`, while `document.py` keeps compatibility wrappers and existing XML primitives continue to come from `document_roles.py`.
22. Finished the remaining `P3` extraction move by introducing `document_extraction.py` for DOCX archive validation, upload-byte reading, paragraph/image extraction, inline run rendering, and list metadata ownership; `document.py` was reduced from the historical monolith to a compact compatibility facade and no longer owns the heavy extraction logic.
23. Closed the post-extraction compatibility regressions by restoring legacy monkeypatch seams in `document.py`, keeping the facade within the SLO at 162 lines while targeted verification passed for `tests/test_document.py`, `tests/test_document_extraction.py`, and `tests/test_document_structure_blocks.py`.
