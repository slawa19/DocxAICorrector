# Project Structure Refactoring Specification

Date: 2026-04-29

Parent context:

- Architectural analysis executed 2026-04-29 covering the full production codebase
- `docs/AI_AGENT_DEVELOPMENT_RULES.md` — anti-god-object policy (section 1.1), module responsibility rules (section 2), anti-patterns (section 5)
- `docs/architecture/session_state_ownership_matrix_2026-04-20.md` — enforced write-ownership contract for `state.py`
- `docs/STARTUP_PERFORMANCE_CONTRACT.md` — protected startup path and forbidden changes
- Existing flat-module structure with 66 production `.py` files at project root, zero packages, zero `__init__.py`

## Goal

Migrate the project from a flat-module root-level structure to a package-based layout, reduce module bloat in monolith files (`app.py`, `config.py`, `models.py`, `processing_runtime.py`), eliminate the duplicated `PreparedRunContext`/`PreparedDocumentData` dataclass pair, and formalize the project as an installable Python package — without changing any runtime behavior, public API contracts, or processing pipeline logic.

This is a **structural-only** refactoring. No functional requirements, no new features, no quality-gate changes, no behavior changes.

## Key Architectural Decision

**All imports must remain backward-compatible.** The refactoring must not break any existing module's public API. Re-exports at the package level and root shim modules must ensure that `from models import ParagraphUnit` continues to work after migration, even though `ParagraphUnit` now physically lives in `docxaicorrector/core/models.py`.

**Migration order: bottom-up.** Move leaf modules first, then intermediate modules, then monoliths. Each step is independently testable and revertible.

**Flat-module killing is a separate concern from monolith decomposition.** These two work streams are orthogonal and must not block each other.

## Non-Goals

Do not implement in this pass:

- Any functional change to processing pipeline, quality gates, image pipeline, or document extraction.
- Any change to `scripts/`, `.vscode/`, `.github/workflows/`, `prompts/`, or `docs/` beyond import-path updates.
- Any change to `streamlit` configuration or runtime behavior.
- Any change to `corpus_registry.toml`, `config.toml`, `.env`, or `requirements.txt`.
- Auto-formatter pass (black, ruff, isort) beyond what is strictly needed to verify imports.
- Removal of root-level files — shim modules must remain at root for backward compatibility during the transition period.
- Type annotation additions beyond what is strictly needed to satisfy `pyright` after imports move.
- Adding or removing any test assertions, fixtures, or test logic — only import-path updates in tests.

## Phase 1: Package-Based Structure

### FR-1.1. Define canonical package layout

Create the following package tree under a new `src/docxaicorrector/` directory. Each sub-package gets an `__init__.py` with explicit `__all__` re-exports of its public API.

```
src/
  docxaicorrector/
    __init__.py                     # top-level re-exports (config, models, logger, constants, ...)
    core/
      __init__.py                   # re-exports: AppConfig, ParagraphUnit, DocumentBlock, ImageAsset, ...
      config.py                     # migrated from root config.py (see Phase 2 for decomposition)
      config_loader_layers.py       # migrated from root
      config_model_registry.py      # migrated from root
      config_runtime_sections.py    # migrated from root
      config_structure_sections.py  # migrated from root
      constants.py                  # migrated from root
      logger.py                     # migrated from root
      models.py                     # migrated from root (see Phase 2 for decomposition)
    document/
      __init__.py                   # re-exports: validate_docx_source_bytes, extract_document_content_..., build_semantic_blocks, build_editing_jobs, ...
      _document.py                  # migrated from root document.py (rename to avoid shadowing package name)
      boundaries.py                 # migrated from root document_boundaries.py
      boundary_review.py            # migrated from root document_boundary_review.py
      extraction.py                 # migrated from root document_extraction.py
      layout_cleanup.py             # migrated from root document_layout_cleanup.py
      relations.py                  # migrated from root document_relations.py
      roles.py                      # migrated from root document_roles.py
      semantic_blocks.py            # migrated from root document_semantic_blocks.py
      shared_xml.py                 # migrated from root document_shared_xml.py
      structure_repair.py           # migrated from root document_structure_repair.py
      tables.py                     # migrated from root document_tables.py
    pipeline/
      __init__.py                   # re-exports: run_document_processing, ...
      _pipeline.py                  # migrated from root document_pipeline.py
      block_execution.py            # migrated from root document_pipeline_block_execution.py
      block_failures.py             # migrated from root document_pipeline_block_failures.py
      contracts.py                  # migrated from root document_pipeline_contracts.py
      job_parsing.py                # migrated from root document_pipeline_job_parsing.py
      late_phases.py                # migrated from root document_pipeline_late_phases.py
      output_validation.py          # migrated from root document_pipeline_output_validation.py
      setup.py                      # migrated from root document_pipeline_setup.py
      support.py                    # migrated from root document_pipeline_support.py
    processing/
      __init__.py                   # re-exports: PreparationService, ProcessingService, ...
      preparation.py                # migrated from root preparation.py
      processing_service.py         # migrated from root
      processing_runtime.py         # migrated from root (see Phase 2 for decomposition)
      restart_store.py              # migrated from root
    image/
      __init__.py                   # re-exports: ImageProcessingContext, process_document_images, ...
      pipeline.py                   # migrated from root image_pipeline.py
      pipeline_policy.py            # migrated from root image_pipeline_policy.py
      analysis.py                   # migrated from root image_analysis.py
      generation.py                 # migrated from root image_generation.py
      prompts.py                    # migrated from root image_prompts.py
      reconstruction.py             # migrated from root image_reconstruction.py
      reinsertion.py                # migrated from root image_reinsertion.py
      shared.py                     # migrated from root image_shared.py
      validation.py                 # migrated from root image_validation.py
      output_policy.py              # migrated from root image_output_policy.py
    structure/
      __init__.py                   # re-exports: recognize_structure, validate_structure_quality, ...
      recognition.py                # migrated from root structure_recognition.py
      validation.py                 # migrated from root structure_validation.py
    generation/
      __init__.py                   # re-exports: generate_markdown_block, convert_markdown_to_docx_bytes, ...
      _generation.py                # migrated from root generation.py
      formatting_transfer.py        # migrated from root
      formatting_diagnostics_retention.py  # migrated from root
      message_formatting.py         # migrated from root
      openai_response_utils.py      # migrated from root
      search.py                     # migrated from root
    ui/
      __init__.py                   # re-exports: render_sidebar, render_result, ...
      _ui.py                        # migrated from root ui.py
      _app.py                       # migrated from root app.py (see Phase 2 for decomposition)
      app_runtime.py                # migrated from root
      application_flow.py           # migrated from root
      compare_panel.py              # migrated from root
    runtime/
      __init__.py                   # re-exports: BackgroundRuntime, ProcessingEvent, ...
      events.py                     # migrated from root runtime_events.py
      artifacts.py                  # migrated from root runtime_artifacts.py
      artifact_retention.py         # migrated from root runtime_artifact_retention.py
      state.py                      # migrated from root state.py
    validation/
      __init__.py                   # re-exports: real_document_validation_*, corpus_registry helpers
      common.py                     # migrated from root real_document_validation_common.py
      profiles.py                   # migrated from root real_document_validation_profiles.py
      structural.py                 # migrated from root real_document_validation_structural.py
    text/
      __init__.py                   # re-exports: assess_text_transform_excerpt, build_text_transform_warnings, ...
      transform_assessment.py       # migrated from root text_transform_assessment.py
      translation_domains.py        # migrated from root
      recommended_text_settings.py  # migrated from root
```

Names with `_` prefix (e.g. `_document.py`, `_pipeline.py`, `_generation.py`, `_ui.py`, `_app.py`) avoid shadowing the package name.

### FR-1.2. Create root-level shim modules for backward compatibility

Each original root-level `.py` file becomes a shim that re-exports from the new package location:

```python
# root/preparation.py (shim)
from docxaicorrector.processing.preparation import *
```

Shim modules must not contain any implementation logic. They serve as redirects during the migration window and can be removed in a future cleanup pass.

### FR-1.3. Update sys.path / PYTHONPATH for the new layout

Add `src/` to the Python path. Preferred approach: `pyproject.toml` with `[tool.pytest.ini_options]` and `pythonpath = ["src"]`, plus a `.pth` file or explicit `sys.path` insertion in entry-point scripts.

The `scripts/test.sh` wrapper must add `src/` to `PYTHONPATH` before invoking `pytest`.

### FR-1.4. All `__init__.py` files must declare `__all__`

Each package's `__init__.py` must explicitly enumerate every public name in `__all__`. This serves as the package's contract and enables `from docxaicorrector.document import *` for shim modules.

### FR-1.5. Tests mirror the package structure

Move test files from `tests/` to `tests/docxaicorrector/{core,document,pipeline,processing,image,structure,generation,ui,runtime,validation,text}/`. Update import paths accordingly.

Root-level `tests/conftest.py` remains at `tests/conftest.py`.

### FR-1.6. Streamlit entry point preserved

`app.py` at project root must remain as the Streamlit `main()` entry point, or a new root `app.py` shim must call `docxaicorrector.ui._app.main()` transparently. The `streamlit run app.py` contract must not break.

### FR-1.7. WSL-first runtime contract preserved

`scripts/test.sh`, VS Code tasks, and all canonical entry points must continue working through the WSL project runtime. The `bash scripts/test.sh ...` path must not regress.

### FR-1.8. Pyright must pass on the new structure

After migration, `pyright src/docxaicorrector` and `pyright tests/docxaicorrector` must produce zero errors. Pyright configuration in `pyrightconfig.json` must be updated to include the new paths.

---

## Phase 2: Monolith Decomposition

### FR-2.1. Decompose `models.py` (1065 lines → multiple files)

Split `models.py` into domain-specific submodules:

```
src/docxaicorrector/core/
  models/
    __init__.py          # re-exports everything for backward compatibility
    paragraph.py         # RawParagraph, RawTable, RawBlock, ParagraphUnit, ParagraphDescriptor, ParagraphClassification
    document.py          # ParagraphBoundaryDecision/Report, ParagraphRelation/Decision/Report, StructureMap, StructureRecognitionSummary
    block.py             # DocumentBlock
    image.py             # ImageAsset, ImageAnalysisResult, ImageValidationResult, ImagePipelineMetadata, ImageVariantCandidate, ImageRuntime*, ImageDelivery*
    structure.py         # StructureRepairDecision/Report, LayoutArtifactCleanupDecision/Report
    enums.py             # ImageMode (and future enums currently in models.py)
```

Each submodule exports a discrete set of related dataclasses. `core/models/__init__.py` re-exports all names, so no import of `ParagraphUnit` breaks.

### FR-2.2. Decompose `config.py` (1038 lines → complete split)

The current `config.py` already has companion files `config_loader_layers.py`, `config_model_registry.py`, `config_runtime_sections.py`, `config_structure_sections.py` — but `config.py` itself remains monolithic.

Move split:

```
src/docxaicorrector/core/
  config/
    __init__.py            # re-exports: load_app_config, AppConfig, LanguageOption, TextModelConfig, ModelRegistry, ...
    loader.py              # TOML + .env parsing, AppConfig construction (the bulk of current config.py)
    models.py              # AppConfig, LanguageOption, TextModelConfig, ModelRegistry dataclasses
    layers.py              # migrated from config_loader_layers.py
    model_registry.py      # migrated from config_model_registry.py
    runtime_sections.py    # migrated from config_runtime_sections.py
    structure_sections.py  # migrated from config_structure_sections.py
```

### FR-2.3. Decompose `app.py` (931 lines → panel components)

Split the monolithic `app.py` into focused UI modules:

```
src/docxaicorrector/ui/
  panels/
    __init__.py
    preparation_panel.py     # render_preparation_panel, preparation polling fragment
    processing_panel.py      # render_processing_panel, processing polling fragment
    upload_panel.py          # file uploader rendering, upload state management
    recommendations_panel.py # recommended text settings UI logic
    result_panel.py          # render_result, render_result_bundle, render_markdown_preview
    controls_panel.py        # sidebar rendering delegation, start/stop controls
  _app.py                    # main() — only orchestration: calls panels, wires threads, event loops (~150-200 lines)
```

Each panel module exports `render_*` functions. `_app.py` imports and calls them. No business logic moves — only the location of the rendering functions.

### FR-2.4. Decompose `processing_runtime.py` (1094 lines → split by responsibility)

```
src/docxaicorrector/processing/
  runtime/
    __init__.py              # re-exports: BackgroundRuntime, start_background_*, drain_*_events, ...
    runtime.py               # BackgroundRuntime class, event-emitting infrastructure
    upload.py                # freeze_uploaded_file, resolve_uploaded_filename, normalize_uploaded_document, format detection
    workers.py               # start_background_processing, start_background_preparation, emit_* helpers
    draining.py              # drain_processing_events, drain_preparation_events, should_stop_processing
```

### FR-2.5. Eliminate `PreparedRunContext` / `PreparedDocumentData` duplication

`application_flow.py:PreparedRunContext` and `preparation.py:PreparedDocumentData` are near-identical dataclasses with 30+ overlapping fields. After the package migration:

1. Define a single canonical `PreparationResult` dataclass in `docxaicorrector.processing.preparation`.
2. `PreparedRunContext` becomes a thin wrapper or type alias pointing to `PreparationResult`.
3. All consumers reference the single canonical type.
4. Remove the duplicate field declarations.

---

## Phase 3: Package Configuration

### FR-3.1. Formalize `pyproject.toml` as an installable package

Add `[project]` section:

```toml
[project]
name = "docxaicorrector"
version = "0.1.0"
description = "AI-powered DOCX editing and translation pipeline"
requires-python = ">=3.12"
dependencies = [
    "openai>=1.68.0",
    "streamlit>=1.42.0",
    "python-docx>=1.1.2",
    "pypandoc>=1.15",
    "python-dotenv>=1.0.1",
    "Pillow>=10.4.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.4.2",
    "pyright>=1.1.400",
]

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["src"]
python_files = ["test_*.py"]
filterwarnings = [
    "ignore::DeprecationWarning:docx.*",
]
markers = [
    "integration: tests that require external tools or broader system setup",
]
```

### FR-3.2. Add `py.typed` marker

Create `src/docxaicorrector/py.typed` (empty file) to signal PEP 561 compliance so type-checkers can resolve the package.

### FR-3.3. Update `.vscode/settings.json` interpreter path

Update `python.defaultInterpreterPath` and add `python.analysis.extraPaths`:

```json
{
    "python.defaultInterpreterPath": "${workspaceFolder}\\.venv-win\\Scripts\\python.exe",
    "python.terminal.activateEnvironment": true,
    "terminal.integrated.defaultProfile.windows": "Command Prompt",
    "python.analysis.extraPaths": ["${workspaceFolder}/src"]
}
```

---

## Non-Functional Requirements

### NFR-1. Zero behavior change

The refactoring must not change any output, any pipeline phase result, any event payload, any log entry, any UI widget rendering, or any file artifact. Only the physical location of `.py` files and the import graph changes.

### NFR-2. Full test suite parity

After every migration step, the full test suite must pass with identical results (pass/fail counts unchanged). No test may flip from pass to fail or fail to pass.

### NFR-3. Incremental, revertible steps

Each migration step must be independently verifiable (run the relevant test subset) and reversable (git revert). Steps must not depend on multiple uncommitted file moves in the working tree.

### NFR-4. WSL-first verification

All verification must use canonical WSL entry points: `bash scripts/test.sh ...`. Agent-side debugging through Windows venv is allowed only as a debug path, not as final verification.

### NFR-5. Protected contracts untouched

The following protected contracts must not regress:
- Test workflow contract (`scripts/test.sh`, `.vscode/tasks.json`, `tests/test_script_workflow_smoke.py`)
- Startup performance contract (`docs/STARTUP_PERFORMANCE_CONTRACT.md`)
- Session state ownership matrix (`state.py` write ownership)
- Anti-god-object policy (`docs/AI_AGENT_DEVELOPMENT_RULES.md` section 1.1)

### NFR-6. Import performance no regression

Package `__init__.py` imports must not introduce circular imports or lazy import overhead. Re-exports must be direct (`from .module import Name`), not wildcard (`from .module import *`).

### NFR-7. Documentation synchronized

After the refactoring, update import-path examples in:
- `README.md`
- `CONTRIBUTING.md`
- `docs/WORKFLOW_AND_IMAGE_MODES.md`
- `.github/copilot-instructions.md`
- `docs/AI_AGENT_DEVELOPMENT_RULES.md`
- `docs/architecture/normal_processing_call_graph.md`

### NFR-8. Pyright clean on final structure

`pyright src/docxaicorrector` and `pyright tests/docxaicorrector` must pass with zero errors on the final structure.

---

## Acceptance Criteria

### AC-1. Package tree exists

All `.py` files listed in FR-1.1 exist at their new paths. No production `.py` file at root except shim modules.

### AC-2. Shim modules forward correctly

```python
python -c "from preparation import PreparedDocumentData; print(type(PreparedDocumentData))"
```

must print the same type as before migration.

### AC-3. Full pytest suite passes

```bash
bash scripts/test.sh tests/ -q
```

Result must be identical to pre-refactoring baseline (same pass/fail/skip counts).

### AC-4. Real-document validation passes

```bash
bash scripts/run-real-document-validation.sh
bash scripts/run-real-document-quality-gate.sh
```

Same outcomes as pre-refactoring baseline.

### AC-5. Streamlit app launches

`streamlit run app.py` must render the application without import errors.

### AC-6. Pyright passes

```bash
pyright src/docxaicorrector
pyright tests/docxaicorrector
```

Zero errors on the new package structure.

### AC-7. No duplicate dataclasses

`PreparedRunContext` and `PreparedDocumentData` no longer define duplicate fields. One canonical type exists in `preparation.py`.

### AC-8. `pyproject.toml` is a valid package definition

```bash
python -m pip install -e ".[dev]"
```

must succeed (in WSL venv). `import docxaicorrector` must work.

### AC-9. `__all__` coverage complete

Every public name exported by each sub-package is listed in its `__init__.py.__all__`. No implicit exports.

### AC-10. Protected contracts verified

```bash
bash scripts/test.sh tests/test_script_workflow_smoke.py -q
bash scripts/test.sh tests/test_startup_performance_contract.py -q
bash scripts/test.sh tests/test_session_state_ownership.py -q
```

All three must pass.

---

## Minimal Test Matrix

After every migration step, run:

```bash
# Phase 1 verification — core structure no regressions
bash scripts/test.sh tests/ -q

# Protected contracts
bash scripts/test.sh tests/test_script_workflow_smoke.py -q
bash scripts/test.sh tests/test_startup_performance_contract.py -q
bash scripts/test.sh tests/test_session_state_ownership.py -q
```

After final migration, additionally run:

```bash
# Real document validation
bash scripts/run-real-document-validation.sh
bash scripts/run-real-document-quality-gate.sh

# Type checking
bash scripts/analyze_pyright.py   # or direct pyright invocation
```

---

## Development Plan

### Step 0. Baseline snapshot

1. Record current test counts (`passed / failed / skipped`) from `bash scripts/test.sh tests/ -q`.
2. Record real-document validation outcomes.
3. Record `pyright` baseline errors.
4. Commit everything with a clean working tree.

This snapshot is the regression target for every subsequent step.

### Step 1. Create package scaffold

- Create `src/docxaicorrector/` directory tree with empty `__init__.py` files.
- Add `__all__ = []` stubs.
- Create root shim modules (empty re-exports).
- Update `pyproject.toml` with `[tool.pytest.ini_options] pythonpath = ["src"]`.
- Update `scripts/test.sh` to add `src/` to `PYTHONPATH`.
- Verify test suite still passes (no files moved yet).

### Step 2. Migrate core modules (bottom-up)

Move these modules, update imports, create shims:

**Batch 2a — utility modules (no internal project deps beyond stdlib):**
- `constants.py` → `docxaicorrector/core/constants.py`
- `logger.py` → `docxaicorrector/core/logger.py`

**Batch 2b — config family:**
- `config.py` + `config_*.py` → `docxaicorrector/core/config*.py`

**Batch 2c — models:**
- `models.py` → `docxaicorrector/core/models.py`

After each batch: run `bash scripts/test.sh tests/test_<module>.py -q && bash scripts/test.sh tests/test_startup_performance_contract.py -q`.

### Step 3. Migrate leaf domain modules

Move modules that don't import other root modules (or only import core):

**Batch 3a:**
- `runtime_events.py` → `docxaicorrector/runtime/events.py`
- `runtime_artifacts.py` → `docxaicorrector/runtime/artifacts.py`
- `runtime_artifact_retention.py` → `docxaicorrector/runtime/artifact_retention.py`
- `translation_domains.py` → `docxaicorrector/text/translation_domains.py`
- `text_transform_assessment.py` → `docxaicorrector/text/transform_assessment.py`
- `recommended_text_settings.py` → `docxaicorrector/text/recommended_text_settings.py`
- `search.py` → `docxaicorrector/generation/search.py`
- `message_formatting.py` → `docxaicorrector/generation/message_formatting.py`

**Batch 3b — structure:**
- `structure_validation.py` → `docxaicorrector/structure/validation.py`
- `structure_recognition.py` → `docxaicorrector/structure/recognition.py`

**Batch 3c — document family:**
- `document_shared_xml.py`, `document_roles.py`, `document_tables.py`
- `document_boundaries.py`, `document_boundary_review.py`
- `document_relations.py`, `document_semantic_blocks.py`
- `document_extraction.py`, `document_layout_cleanup.py`
- `document_structure_repair.py`
- `document.py` → `docxaicorrector/document/_document.py`

**Batch 3d — validation:**
- `real_document_validation_common.py` → `docxaicorrector/validation/common.py`
- `real_document_validation_profiles.py` → `docxaicorrector/validation/profiles.py`
- `real_document_validation_structural.py` → `docxaicorrector/validation/structural.py`

After each batch: run affected test files and the full suite at the end of step 3.

### Step 4. Migrate pipeline family

Move all `document_pipeline*.py` files to `docxaicorrector/pipeline/`. These have internal cross-imports — move them as one atomic batch.

After: `bash scripts/test.sh tests/test_document_pipeline*.py -q && bash scripts/test.sh tests/test_document_pipeline_output_validation.py -q && bash scripts/test.sh tests/test_document_pipeline_failures.py -q`.

### Step 5. Migrate image family

Move all `image_*.py` files to `docxaicorrector/image/`. Same atomic batch approach.

After: `bash scripts/test.sh tests/test_image_*.py -q`.

### Step 6. Migrate processing family

Move:
- `preparation.py` → `docxaicorrector/processing/preparation.py`
- `processing_service.py` → `docxaicorrector/processing/processing_service.py`
- `processing_runtime.py` → `docxaicorrector/processing/processing_runtime.py`
- `restart_store.py` → `docxaicorrector/processing/restart_store.py`
- `state.py` → `docxaicorrector/runtime/state.py`
- `workflow_state.py` → `docxaicorrector/runtime/workflow_state.py`

After: full test suite.

### Step 7. Migrate generation family

Move:
- `generation.py` → `docxaicorrector/generation/_generation.py`
- `formatting_transfer.py` → `docxaicorrector/generation/formatting_transfer.py`
- `formatting_diagnostics_retention.py` → `docxaicorrector/generation/formatting_diagnostics_retention.py`
- `openai_response_utils.py` → `docxaicorrector/generation/openai_response_utils.py`

After: `bash scripts/test.sh tests/test_generation.py -q && bash scripts/test.sh tests/test_format_restoration.py -q`.

### Step 8. Migrate UI family

Move:
- `ui.py` → `docxaicorrector/ui/_ui.py`
- `app_runtime.py` → `docxaicorrector/ui/app_runtime.py`
- `application_flow.py` → `docxaicorrector/ui/application_flow.py`
- `compare_panel.py` → `docxaicorrector/ui/compare_panel.py`
- `app.py` → `docxaicorrector/ui/_app.py`

The root `app.py` becomes a shim:

```python
# root/app.py
from docxaicorrector.ui._app import main

if __name__ == "__main__":
    main()
```

### Step 9. Move tests

Mirror the package structure under `tests/docxaicorrector/`. Run full suite.

### Step 10. Monolith decomposition (Phase 2)

Apply FR-2.1 through FR-2.5, one at a time. Each step requires the relevant test subset to pass.

### Step 11. Package formalization (Phase 3)

Apply FR-3.1 through FR-3.3. Verify `pip install -e .` works, `streamlit run app.py` launches, and full test suite passes.

### Step 12. Documentation sync

Update all canonical docs listed in NFR-7.

### Step 13. Final verification

Run:
```bash
# Full test suite
bash scripts/test.sh tests/ -q

# Protected contracts
bash scripts/test.sh tests/test_script_workflow_smoke.py -q
bash scripts/test.sh tests/test_startup_performance_contract.py -q
bash scripts/test.sh tests/test_session_state_ownership.py -q

# Real document validation
bash scripts/run-real-document-validation.sh
bash scripts/run-real-document-quality-gate.sh

# Type checking
pyright src/docxaicorrector
pyright tests/docxaicorrector
```

All must pass. Test counts must match Step 0 baseline.

---

## Risks and Mitigations

### R-1. Import cycle detection after package moves

**Risk:** Modules that currently import each other via flat-module paths may form import cycles when placed in separate packages.

**Mitigation:** Each migration batch is followed by immediate test verification. If `pytest` fails on an import cycle, the problematic module(s) can be deferred to a later batch or restructured with lazy imports. The refactoring spec explicitly allows deferring individual modules to a future pass if cycle resolution would require behavioral changes.

### R-2. Shims create confusion about canonical module location

**Risk:** Developers may edit the root shim instead of the actual module in `src/docxaicorrector/`.

**Mitigation:** Each shim file has a header comment: `# SHIM: redirects to docxaicorrector.xxx.xxx. Edit the source, not this file.`. Additionally, the shim files are 1-2 lines (just `from ... import *`) — editing them is obviously wrong.

### R-3. `streamlit run app.py` breaks on shim indirection

**Risk:** Streamlit's module watcher or reload logic may not follow shim imports correctly.

**Mitigation:** After Step 8, launch the application in WSL and smoke-test: upload a .docx, run preparation, verify UI renders. If Streamlit shows import errors, the shim can inline the `main()` call rather than forwarding:

```python
# root/app.py (shim, alternative form)
from docxaicorrector.ui._app import main

if __name__ == "__main__":
    main()
```

should be safe since `streamlit run app.py` executes `app.py` as `__main__`.

### R-4. Pyright configuration breakage

**Risk:** Moving files changes pyright's resolution paths, producing false-positive errors.

**Mitigation:** `pyrightconfig.json` is updated alongside Step 1 to include `src/` and `tests/` in `include` / `extraPaths`. The `pyright` check is run after every major batch.

### R-5. Test import paths need mass-update

**Risk:** 65 test files need import-path updates, creating noise and merge-conflict risk.

**Mitigation:** Tests use the shim modules during the transition. After all production code is moved, tests are updated in a single atomic batch (Step 9). A helper script or `sed` pass can automate the path replacement.

### R-6. CI breaks on new directory structure

**Risk:** GitHub Actions `ci.yml` currently runs `pytest` from the project root with `bash scripts/test.sh ...`. Moving files may require CI updates.

**Mitigation:** CI uses `bash scripts/test.sh tests/ -q` which is the canonical entry point. As long as `scripts/test.sh` is updated (Step 1), CI is covered. The `ci.yml` file itself needs no changes — all path resolution happens in `scripts/test.sh`.

### R-7. Merge conflicts with active development

**Risk:** Other specs (PDF quality hardening, audiobook preparation) are actively developed. File moves create large diffs that conflict with feature branches.

**Mitigation:** Phase 1 (package creation + shims) should be done in a dedicated branch, merged to main, and then feature branches rebase onto it. Phase 2 (monolith decomposition) is lower-priority and can be spread over multiple smaller PRs. Phase 3 is purely additive and conflicts minimally.

---

## Done Criteria

This refactoring is complete when:

1. All production `.py` code lives under `src/docxaicorrector/` in the structure defined by FR-1.1.
2. Root `.py` files are shims only (1-3 lines each).
3. Test files mirror the package structure under `tests/docxaicorrector/`.
4. Full `pytest` suite passes with identical pass/fail counts as the baseline snapshot.
5. Real-document validation passes for all registered corpus profiles.
6. Streamlit application launches and renders without import errors.
7. `pyright src/docxaicorrector && pyright tests/docxaicorrector` produces zero errors.
8. `pyproject.toml` defines an installable package; `pip install -e .` succeeds.
9. `PreparedRunContext` and `PreparedDocumentData` are unified into a single canonical type.
10. All canonical documentation references updated import paths.
11. All protected contracts (`test_script_workflow_smoke`, `test_startup_performance_contract`, `test_session_state_ownership`) pass without changes to their logic.
