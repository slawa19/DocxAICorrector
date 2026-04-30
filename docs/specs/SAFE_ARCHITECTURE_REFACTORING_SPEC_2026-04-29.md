# Safe Architecture Refactoring Specification

Date: 2026-04-29

Supersedes draft: `docs/specs/PROJECT_STRUCTURE_REFACTORING_SPEC_2026-04-29.md`

Status: implementation-ready specification after correctness review of the initial draft.

## Goal

Move the project from flat root-level production modules to a `src/docxaicorrector/` package layout while preserving every current runtime contract:

- `streamlit run app.py` continues to launch the same application.
- Existing imports such as `import config`, `from models import ParagraphUnit`, and `import preparation` continue to work.
- Monkeypatching root modules in tests continues to affect the implementation module.
- Canonical WSL commands continue to be the source of truth.
- Real-document validation, benchmark runners, VS Code tasks, CI workflow contracts, startup performance, and session-state ownership remain protected.

This is a structural-only refactoring. It must not change processing behavior, UI behavior, event payloads, log semantics, quality gates, document extraction, image processing, or generated artifacts.

## Non-Goals

Do not implement in this refactoring:

- New product features.
- Pipeline logic changes.
- Quality-gate threshold changes.
- Image-processing logic changes.
- Streamlit layout or widget behavior changes.
- Broad formatting-only rewrites.
- Monolith decomposition in the same PR as the package migration.
- Removal of root-level compatibility modules.

Allowed changes despite being protected files:

- Minimal path/bootstrap updates in `scripts/`, `.vscode/`, `.github/workflows/ci.yml`, `.github/CODEOWNERS`, `pyproject.toml`, `pyrightconfig.json`, and tests when required to preserve existing contracts under the new package layout.
- Documentation import-path updates after code migration is complete.
- Test updates that are required by path relocation or protected-contract relocation. Test assertions must continue to assert the same behavior and contract intent.

## Safety Principles

1. Move code bottom-up and verify after every batch.
2. Keep each batch revertible.
3. Never create a root shim before the implementation module exists in the package.
4. Root shims must be module aliases, not wildcard re-export copies.
5. Do not move tests until production imports and root aliases are stable.
6. Keep protected contract tests at root unless a dedicated contract-update batch moves them and updates every caller, CODEOWNERS entry, VS Code task assertion, and CI command.
7. Compute repository paths independently from the physical package file location.
8. Use canonical WSL entrypoints for final verification.
9. Keep package `__init__.py` files lightweight; do not force heavy imports during `import docxaicorrector`.
10. Defer file-to-package monolith decomposition to a later phase after the package migration is green.

## Current Protected Contracts

The migration must preserve these current contracts unless explicitly updated in the same batch and verified by their protected tests:

- `scripts/test.sh` is the canonical pytest entrypoint.
- `.vscode/tasks.json` test tasks invoke `bash scripts/test.sh` through WSL.
- `.github/workflows/ci.yml` invokes `bash scripts/test.sh tests/test_script_workflow_smoke.py -q`, `bash scripts/test.sh tests/test_startup_performance_contract.py -q`, and `bash scripts/test.sh tests/ -q`.
- `tests/test_script_workflow_smoke.py` validates workflow, CI, VS Code task, CODEOWNERS, and setup contracts.
- `tests/test_startup_performance_contract.py` validates startup import budget and monkeypatches `config` and `generation` module globals.
- `tests/test_session_state_ownership.py` enforces session-state write ownership.
- `tests/test_typecheck.py` runs `sys.executable -m pyright --outputjson` with zero-error baseline.
- `.github/CODEOWNERS` protects root `app.py`, `config.py`, `generation.py`, scripts, docs, and key tests.

## Compatibility Requirements

### Root Module Aliases

Each moved root module must become a module alias shim, not a `from target import *` shim.

Required shim pattern:

```python
"""Compatibility alias for the migrated implementation module."""

from importlib import import_module
from pathlib import Path
import sys

_SRC = Path(__file__).resolve().parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

_target = import_module("docxaicorrector.processing.preparation")
sys.modules[__name__] = _target
```

Reason: tests and callers currently monkeypatch module globals. A wildcard shim copies names into the shim namespace and breaks mutation identity. A `sys.modules` alias preserves `import config`, `monkeypatch.setattr(config, "_CLIENT", None)`, private helper access, and `module.__dict__` identity.

Bootstrap rule: every root compatibility shim or executable wrapper must make `src/` importable by inserting `Path(__file__).resolve().parent / "src"` before importing `docxaicorrector`. Do not rely on pytest-only `pythonpath`, shell-script `PYTHONPATH`, or editable install state for root compatibility. Root imports such as `python -c "import config"` and direct root script execution must continue to work from the repository root without external environment preparation.

Acceptance check for every shim:

```bash
python -c "import config; import docxaicorrector.core.config as target; assert config is target"
```

For class/function exports, identity must also hold:

```bash
python -c "from preparation import PreparedDocumentData as A; from docxaicorrector.processing.preparation import PreparedDocumentData as B; assert A is B"
```

### Executable Compatibility Wrappers

Modules that are imported as compatibility modules and also executed as scripts need a split wrapper. A plain `sys.modules[__name__] = target` shim is correct for normal imports but does not execute the target module's `if __name__ == "__main__"` block when the root file is run directly.

Required executable wrapper pattern:

```python
"""Compatibility wrapper for the migrated CLI-capable module."""

from importlib import import_module
from pathlib import Path
import sys

_SRC = Path(__file__).resolve().parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

_TARGET = "docxaicorrector.validation.structural"

if __name__ == "__main__":
    from docxaicorrector.validation.structural import main

    raise SystemExit(main())

_target = import_module(_TARGET)
sys.modules[__name__] = _target
```

This pattern is required for root modules that retain direct script execution, including `real_document_validation_structural.py` and `real_image_manifest.py` if their root filenames remain executable. Alternatively, the calling script may be updated to use `python -m docxaicorrector.<package>.<module>`, but that update must happen in the same batch and be covered by the verification command.

### App Module Compatibility

Root `app.py` is both the Streamlit entrypoint and an imported module in tests. The wrapper must preserve both roles. A minimal `from docxaicorrector.ui._app import main` wrapper is not sufficient because tests access many module-level and private names through `app.<name>`.

Required root `app.py` form after UI migration:

```python
from pathlib import Path
from importlib import import_module
import sys as _sys

_SRC = Path(__file__).resolve().parent / "src"
if str(_SRC) not in _sys.path:
    _sys.path.insert(0, str(_SRC))

if __name__ == "__main__":
    from docxaicorrector.ui._app import main

    main()
else:
    _target = import_module("docxaicorrector.ui._app")
    _sys.modules[__name__] = _target
```

Acceptance checks:

```bash
python -c "import app; import docxaicorrector.ui._app as target; assert app is target"
python -c "import app; assert hasattr(app, '_resolve_sidebar_settings'); assert hasattr(app, 'main')"
```

### Repository Root Resolution

`constants.py` currently derives paths from `Path(__file__).resolve().parent`. After migration this would point to `src/docxaicorrector/core`, which is wrong.

Before moving `constants.py`, introduce a root resolver that is stable from both root and package locations:

```python
def resolve_repo_root(start: Path) -> Path:
    for candidate in (start, *start.parents):
        if (candidate / "config.toml").exists() and (candidate / "prompts").is_dir() and (candidate / "pyproject.toml").exists():
            return candidate
    raise RuntimeError("Could not resolve DocxAICorrector repository root")
```

`BASE_DIR`, `PROMPTS_DIR`, `ENV_PATH`, `CONFIG_PATH`, `RUN_DIR`, `UI_RESULT_ARTIFACTS_DIR`, and log paths must resolve to the same absolute paths before and after the move.

Add or update a focused test before the move:

```python
def test_constants_paths_resolve_to_repo_root():
    from pathlib import Path

    import constants

    repo_root = Path(__file__).resolve().parents[1]

    assert constants.BASE_DIR == repo_root
    assert constants.CONFIG_PATH == repo_root / "config.toml"
    assert constants.PROMPTS_DIR == repo_root / "prompts"
    assert constants.RUN_DIR == repo_root / ".run"
```

### Package Init Policy

Package `__init__.py` files must be lightweight.

Rules:

- `docxaicorrector/__init__.py` may expose metadata and lightweight constants only.
- Subpackage `__init__.py` files may re-export stable public names only when doing so does not import heavy runtime dependencies or create cycles.
- Root compatibility is provided by root alias shims, not by top-level `docxaicorrector` eager imports.
- Every non-empty `__all__` must be explicit.
- Empty `__all__ = []` is allowed during scaffold and intermediate migration.

### Source Path Bootstrap

All canonical entrypoints must be able to import `docxaicorrector` before root modules are removed or after root shims are created.

Required updates:

- `pyproject.toml`: add `pythonpath = ["src", "."]` under `[tool.pytest.ini_options]` during transition.
- `scripts/test.sh`: export `PYTHONPATH="$PWD/src:$PWD${PYTHONPATH:+:$PYTHONPATH}"` after `cd` and before invoking pytest.
- `scripts/run-real-document-validation.sh`: export the same `PYTHONPATH`.
- `scripts/run-structural-preparation-diagnostic.sh`: export the same `PYTHONPATH`.
- `scripts/run-real-document-quality-gate.sh`: covered through `scripts/test.sh`, but keep it in the verification matrix.
- Root `app.py`: use the App Module Compatibility wrapper above so `streamlit run app.py`, `python -c "import app"`, and `tests/test_app*.py` all see the target `_app` module.
- `tests/conftest.py`: ensure the resulting `sys.path` order places `PROJECT_ROOT / "src"` before `PROJECT_ROOT` so pytest fixture imports work deterministically with package imports and root aliases.
- Benchmark and utility entrypoints: ensure the resulting `sys.path` order places `REPO_ROOT / "src"` or `ROOT_DIR / "src"` before the repository root where they currently bootstrap only root paths.

Implementation note: the required contract is the effective import resolution order, not the textual order of statements. When using repeated `sys.path.insert(0, ...)`, code may insert the repository root first and `src` second as long as the final `sys.path` order is `src`, then repository root.
- Root compatibility shims and executable wrappers: insert repository `src/` directly in the shim/wrapper file before importing `docxaicorrector`; this is required because verification commands and backward-compatible root imports must work even outside pytest and outside shell-script wrappers.

This explicit path insertion is required during the transition even if editable install later works, because scripts and tests currently run from source without relying on installation state.

Verification rule for direct Python commands: every `python -c ...` or `python -m ...` command in this specification is expected to pass from the repository root without manually exporting `PYTHONPATH`, because the compatibility layer itself must bootstrap `src/`. If a batch intentionally verifies package imports before the root shim exists, it may temporarily use `PYTHONPATH=src:. ...` for that pre-shim intra-batch check, but final acceptance for the batch must include the plain command form shown in this spec.

## Target Package Layout

Create this package tree. The listed files are target implementation locations, not necessarily all created in the first batch.

```text
src/
  docxaicorrector/
    __init__.py
    py.typed
    core/
      __init__.py
      config.py
      config_loader_layers.py
      config_model_registry.py
      config_runtime_sections.py
      config_structure_sections.py
      constants.py
      logger.py
      models.py
    document/
      __init__.py
      _document.py
      boundaries.py
      boundary_review.py
      extraction.py
      layout_cleanup.py
      relations.py
      roles.py
      semantic_blocks.py
      shared_xml.py
      structure_repair.py
      tables.py
    pipeline/
      __init__.py
      _pipeline.py
      block_execution.py
      block_failures.py
      contracts.py
      job_parsing.py
      late_phases.py
      output_validation.py
      setup.py
      support.py
    processing/
      __init__.py
      preparation.py
      processing_runtime.py
      processing_service.py
      restart_store.py
    image/
      __init__.py
      analysis.py
      generation.py
      output_policy.py
      pipeline.py
      pipeline_policy.py
      prompts.py
      reconstruction.py
      reinsertion.py
      shared.py
      validation.py
    structure/
      __init__.py
      recognition.py
      validation.py
    generation/
      __init__.py
      _generation.py
      formatting_diagnostics_retention.py
      formatting_transfer.py
      message_formatting.py
      openai_response_utils.py
      search.py
    ui/
      __init__.py
      _app.py
      _ui.py
      app_runtime.py
      application_flow.py
      compare_panel.py
      recommended_text_settings.py
    runtime/
      __init__.py
      artifact_retention.py
      artifacts.py
      events.py
      state.py
      workflow_state.py
    validation/
      __init__.py
      common.py
      profiles.py
      structural.py
    text/
      __init__.py
      transform_assessment.py
      translation_domains.py
    real_image/
      __init__.py
      manifest.py
```

## Module Inventory

Every current root production module must have one target path and one root alias shim.

| Current root module | Target implementation path |
| --- | --- |
| `app.py` | `src/docxaicorrector/ui/_app.py` plus special root Streamlit entrypoint |
| `app_runtime.py` | `src/docxaicorrector/ui/app_runtime.py` |
| `application_flow.py` | `src/docxaicorrector/ui/application_flow.py` |
| `compare_panel.py` | `src/docxaicorrector/ui/compare_panel.py` |
| `ui.py` | `src/docxaicorrector/ui/_ui.py` |
| `config.py` | `src/docxaicorrector/core/config.py` |
| `config_loader_layers.py` | `src/docxaicorrector/core/config_loader_layers.py` |
| `config_model_registry.py` | `src/docxaicorrector/core/config_model_registry.py` |
| `config_runtime_sections.py` | `src/docxaicorrector/core/config_runtime_sections.py` |
| `config_structure_sections.py` | `src/docxaicorrector/core/config_structure_sections.py` |
| `constants.py` | `src/docxaicorrector/core/constants.py` |
| `logger.py` | `src/docxaicorrector/core/logger.py` |
| `models.py` | `src/docxaicorrector/core/models.py` |
| `document.py` | `src/docxaicorrector/document/_document.py` |
| `document_boundaries.py` | `src/docxaicorrector/document/boundaries.py` |
| `document_boundary_review.py` | `src/docxaicorrector/document/boundary_review.py` |
| `document_extraction.py` | `src/docxaicorrector/document/extraction.py` |
| `document_layout_cleanup.py` | `src/docxaicorrector/document/layout_cleanup.py` |
| `document_relations.py` | `src/docxaicorrector/document/relations.py` |
| `document_roles.py` | `src/docxaicorrector/document/roles.py` |
| `document_semantic_blocks.py` | `src/docxaicorrector/document/semantic_blocks.py` |
| `document_shared_xml.py` | `src/docxaicorrector/document/shared_xml.py` |
| `document_structure_repair.py` | `src/docxaicorrector/document/structure_repair.py` |
| `document_tables.py` | `src/docxaicorrector/document/tables.py` |
| `document_pipeline.py` | `src/docxaicorrector/pipeline/_pipeline.py` |
| `document_pipeline_block_execution.py` | `src/docxaicorrector/pipeline/block_execution.py` |
| `document_pipeline_block_failures.py` | `src/docxaicorrector/pipeline/block_failures.py` |
| `document_pipeline_contracts.py` | `src/docxaicorrector/pipeline/contracts.py` |
| `document_pipeline_job_parsing.py` | `src/docxaicorrector/pipeline/job_parsing.py` |
| `document_pipeline_late_phases.py` | `src/docxaicorrector/pipeline/late_phases.py` |
| `document_pipeline_output_validation.py` | `src/docxaicorrector/pipeline/output_validation.py` |
| `document_pipeline_setup.py` | `src/docxaicorrector/pipeline/setup.py` |
| `document_pipeline_support.py` | `src/docxaicorrector/pipeline/support.py` |
| `preparation.py` | `src/docxaicorrector/processing/preparation.py` |
| `processing_runtime.py` | `src/docxaicorrector/processing/processing_runtime.py` |
| `processing_service.py` | `src/docxaicorrector/processing/processing_service.py` |
| `restart_store.py` | `src/docxaicorrector/processing/restart_store.py` |
| `image_analysis.py` | `src/docxaicorrector/image/analysis.py` |
| `image_generation.py` | `src/docxaicorrector/image/generation.py` |
| `image_output_policy.py` | `src/docxaicorrector/image/output_policy.py` |
| `image_pipeline.py` | `src/docxaicorrector/image/pipeline.py` |
| `image_pipeline_policy.py` | `src/docxaicorrector/image/pipeline_policy.py` |
| `image_prompts.py` | `src/docxaicorrector/image/prompts.py` |
| `image_reconstruction.py` | `src/docxaicorrector/image/reconstruction.py` |
| `image_reinsertion.py` | `src/docxaicorrector/image/reinsertion.py` |
| `image_shared.py` | `src/docxaicorrector/image/shared.py` |
| `image_validation.py` | `src/docxaicorrector/image/validation.py` |
| `real_image_manifest.py` | `src/docxaicorrector/real_image/manifest.py` |
| `structure_recognition.py` | `src/docxaicorrector/structure/recognition.py` |
| `structure_validation.py` | `src/docxaicorrector/structure/validation.py` |
| `generation.py` | `src/docxaicorrector/generation/_generation.py` |
| `formatting_diagnostics_retention.py` | `src/docxaicorrector/generation/formatting_diagnostics_retention.py` |
| `formatting_transfer.py` | `src/docxaicorrector/generation/formatting_transfer.py` |
| `message_formatting.py` | `src/docxaicorrector/generation/message_formatting.py` |
| `openai_response_utils.py` | `src/docxaicorrector/generation/openai_response_utils.py` |
| `search.py` | `src/docxaicorrector/generation/search.py` |
| `runtime_artifact_retention.py` | `src/docxaicorrector/runtime/artifact_retention.py` |
| `runtime_artifacts.py` | `src/docxaicorrector/runtime/artifacts.py` |
| `runtime_events.py` | `src/docxaicorrector/runtime/events.py` |
| `state.py` | `src/docxaicorrector/runtime/state.py` |
| `workflow_state.py` | `src/docxaicorrector/runtime/workflow_state.py` |
| `real_document_validation_common.py` | `src/docxaicorrector/validation/common.py` |
| `real_document_validation_profiles.py` | `src/docxaicorrector/validation/profiles.py` |
| `real_document_validation_structural.py` | `src/docxaicorrector/validation/structural.py` |
| `text_transform_assessment.py` | `src/docxaicorrector/text/transform_assessment.py` |
| `translation_domains.py` | `src/docxaicorrector/text/translation_domains.py` |
| `recommended_text_settings.py` | `src/docxaicorrector/ui/recommended_text_settings.py` |

Non-root production/support entrypoints requiring path review:

- `tests/artifacts/real_document_pipeline/run_lietaer_validation.py`
- `benchmark_projects/pdf_candidate_benchmark/benchmark_runner.py`
- `benchmark_projects/pdf_candidate_benchmark/tests/test_benchmark_runner.py`
- `scripts/run_pic1_modes.py`
- `scripts/_run_cleanup_now.py`
- `scripts/_list_log_events.py`
- scripts under `scripts/` that import project modules or run Python scripts

## Import Rewrite Policy

During the transition, implementation modules may continue to use root imports if root alias shims are already present and identity-preserving. This minimizes behavioral risk.

Final package-internal imports should be migrated gradually after all modules are moved:

- Prefer explicit absolute imports from `docxaicorrector.<subpackage>.<module>`.
- Do not mix large import rewrites with physical file moves unless needed to break an import cycle.
- If an import cycle appears, defer that module or batch rather than adding lazy imports that affect startup or runtime semantics.

## Test Layout Policy

Do not move tests during the initial package migration.

Rationale:

- Current workflow, CI, VS Code task, CODEOWNERS, and protected-contract tests hardcode root `tests/test_*.py` paths.
- Moving tests creates test-contract churn unrelated to production package migration.
- The package migration can be fully verified while tests remain in place.

Optional later test-layout phase:

- Move non-protected tests under `tests/docxaicorrector/...` only after production migration is complete and green.
- Keep protected tests at root unless all protected path references are updated in one dedicated batch.
- Update `.github/CODEOWNERS`, `.github/workflows/ci.yml`, `.vscode/tasks.json`, and `tests/test_script_workflow_smoke.py` in the same batch if protected tests move.

## Package Configuration

### Phase 1 Transitional Configuration

Update `pyproject.toml` only as needed for pytest pathing:

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["src", "."]
python_files = ["test_*.py"]
filterwarnings = [
  "ignore::DeprecationWarning:docx.*",
]
markers = [
  "integration: tests that require external tools or broader system setup",
]
```

### Phase 3 Installable Package Configuration

After the package migration is green, add installable package metadata:

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
```

Dependency source-of-truth rule:

- Until CI/setup scripts are migrated, `requirements.txt` remains the CI/setup dependency source.
- `pyproject.toml` must mirror `requirements.txt` dependency constraints exactly for shared dependencies.
- If a later change makes `pyproject.toml` the source of truth, CI, setup scripts, and workflow tests must be updated in the same batch.

Recommended guard if dependency metadata changes again: add a focused test that parses `requirements.txt` and `pyproject.toml` and verifies that every runtime/dev dependency constraint present in both files has the same specifier. Do not introduce divergent version ranges silently.

### Pyright Configuration

Update `pyrightconfig.json` alongside the scaffold:

```json
{
  "pythonVersion": "3.13",
  "typeCheckingMode": "basic",
  "include": ["src/docxaicorrector", "tests", "benchmark_projects", "scripts"],
  "extraPaths": ["src", "."],
  "reportMissingImports": "warning",
  "reportMissingModuleSource": "none"
}
```

Keep `tests/test_typecheck.py` aligned with this config. Current `pythonVersion` is `3.13`; do not lower it as part of this structural refactoring unless a separate type-check/runtime decision is made and verified. CI's Python runtime version and Pyright's configured language version are separate contracts.

Changing `include` changes the type-check surface. The migration batch that edits `pyrightconfig.json` must run `tests/test_typecheck.py` before and after the change. The zero-error baseline must remain zero; if the scope change reveals new errors, fix those errors in the same batch rather than hiding them. If a file is intentionally removed from type-check scope, document that as a protected-contract change and update `tests/test_typecheck.py` in the same batch.

The canonical protected check remains:

```bash
bash scripts/test.sh tests/test_typecheck.py -q
```

Optional direct final checks:

```bash
pyright src/docxaicorrector
pyright tests
```

Do not use `bash scripts/analyze_pyright.py`. If JSON analysis is needed, use:

```bash
pyright --outputjson | python scripts/analyze_pyright.py
```

## Execution Plan

### Step 0. Baseline Snapshot

Record current outcomes before any migration:

```bash
bash scripts/test.sh tests/ -q
bash scripts/test.sh tests/test_script_workflow_smoke.py -q
bash scripts/test.sh tests/test_startup_performance_contract.py -q
bash scripts/test.sh tests/test_session_state_ownership.py -q
bash scripts/test.sh tests/test_typecheck.py -q
bash scripts/run-real-document-validation.sh
bash scripts/run-real-document-quality-gate.sh
```

Record pass/fail/skip counts and real-document outcomes. The workspace should be clean before starting a migration batch.

### Step 1. Bootstrap Package Scaffold

Create directories and lightweight `__init__.py` files under `src/docxaicorrector/`.

Create `src/docxaicorrector/py.typed`.

Add `pythonpath = ["src", "."]` to `pyproject.toml`.

Update `scripts/test.sh`, `scripts/run-real-document-validation.sh`, and `scripts/run-structural-preparation-diagnostic.sh` to export `PYTHONPATH="$PWD/src:$PWD${PYTHONPATH:+:$PYTHONPATH}"`.

Update `tests/conftest.py` to insert `PROJECT_ROOT / "src"` before `PROJECT_ROOT`.

Update `pyrightconfig.json` with `include` and `extraPaths` while preserving `pythonVersion: "3.13"`.

Update bootstrap-sensitive non-root entrypoints that currently insert only the repository root into `sys.path` so they prefer `src` before the repository root. This batch must include at least:

- `tests/artifacts/real_document_pipeline/run_lietaer_validation.py`
- `benchmark_projects/pdf_candidate_benchmark/benchmark_runner.py`
- `scripts/run_pic1_modes.py`

Update bootstrap-sensitive tests that assert exact environment snapshots when needed. In particular, any test that currently expects `PYTHONPATH == "."` must be updated to reflect the new `src`-first transition contract.

Update `tests/test_script_workflow_smoke.py` in the same batch so the protected workflow contract explicitly checks the `src`-first bootstrap in canonical scripts.

Do not create root shims in this step.

Verification:

```bash
bash scripts/test.sh tests/test_script_workflow_smoke.py -q
bash scripts/test.sh tests/test_startup_performance_contract.py -q
bash scripts/test.sh tests/test_typecheck.py -q
bash scripts/test.sh tests/test_real_document_pipeline_validation.py -q
```

Step-1 required assertions in the verification surface:

- canonical scripts export `PYTHONPATH="$PWD/src:$PWD${PYTHONPATH:+:$PYTHONPATH}"`
- `tests/conftest.py` and bootstrap-sensitive entrypoints produce an effective `sys.path` order with `src` before the repository root
- environment snapshot tests accept the `src`-first `PYTHONPATH` contract

### Step 2. Prepare Path-Stable Core Constants

Before moving `constants.py`, make its path resolution independent from `__file__.parent`.

Add or update focused tests for `BASE_DIR`, `PROMPTS_DIR`, `CONFIG_PATH`, `ENV_PATH`, `RUN_DIR`, and UI result artifact paths.

Verification:

```bash
bash scripts/test.sh tests/test_config.py -q
bash scripts/test.sh tests/test_startup_performance_contract.py -q
```

### Step 3. Move Leaf Core Modules

Move:

- `constants.py` to `src/docxaicorrector/core/constants.py`
- `logger.py` to `src/docxaicorrector/core/logger.py`

Create root alias shims only after the target files exist.

Update imports only where required.

Verification:

```bash
bash scripts/test.sh tests/test_logger.py -q
bash scripts/test.sh tests/test_config.py -q
bash scripts/test.sh tests/test_startup_performance_contract.py -q
python -c "import constants; import docxaicorrector.core.constants as target; assert constants is target"
python -c "import logger; import docxaicorrector.core.logger as target; assert logger is target"
```

### Step 4. Move Config Family

Move as one dependency-aware batch:

- `config.py`
- `config_loader_layers.py`
- `config_model_registry.py`
- `config_runtime_sections.py`
- `config_structure_sections.py`

Order inside the batch is mandatory:

1. Create all five target files under `src/docxaicorrector/core/` first.
2. Verify that package imports can resolve using temporary root imports or adjusted imports.
3. Replace all five root files with alias shims in one patch.
4. Run verification immediately.

Do not move `config.py` first while its dependency modules are still neither target files nor root shims. `config.py` imports `config_loader_layers`, `config_model_registry`, `config_runtime_sections`, and `config_structure_sections`, so a partial intra-batch state is not a valid checkpoint.

Do not decompose `config.py` in this step.

Verification:

```bash
bash scripts/test.sh tests/test_config.py -q
bash scripts/test.sh tests/test_model_registry_sweep.py -q
bash scripts/test.sh tests/test_startup_performance_contract.py -q
python -c "import config; import docxaicorrector.core.config as target; assert config is target"
```

### Step 5. Move Models

Move `models.py` to `src/docxaicorrector/core/models.py` and create root alias shim.

Do not split `models.py` into a package in this phase.

Verification:

```bash
bash scripts/test.sh tests/test_document_structure_blocks.py -q
bash scripts/test.sh tests/test_image_validation.py -q
python -c "import models; import docxaicorrector.core.models as target; assert models is target"
```

### Step 6. Move Runtime and Text Leaf Modules

Move dependency-aware batches:

- `runtime_artifact_retention.py`
- `runtime_artifacts.py`
- `runtime_events.py`
- `translation_domains.py`
- `text_transform_assessment.py`
- `recommended_text_settings.py`
- `workflow_state.py`
- `restart_store.py`

Target paths must follow the inventory table.

Verification:

```bash
bash scripts/test.sh tests/test_runtime_artifact_retention.py -q
bash scripts/test.sh tests/test_runtime_artifacts.py -q
bash scripts/test.sh tests/test_translation_domains.py -q
bash scripts/test.sh tests/test_text_transform_assessment.py -q
bash scripts/test.sh tests/test_recommended_text_settings.py -q
bash scripts/test.sh tests/test_workflow_state.py -q
bash scripts/test.sh tests/test_restart_store.py -q
```

### Step 7. Move Structure and Document Family

Move structure modules first:

- `structure_validation.py`
- `structure_recognition.py`

Then move document modules as one atomic family:

- `document_shared_xml.py`
- `document_roles.py`
- `document_tables.py`
- `document_boundaries.py`
- `document_boundary_review.py`
- `document_relations.py`
- `document_semantic_blocks.py`
- `document_extraction.py`
- `document_layout_cleanup.py`
- `document_structure_repair.py`
- `document.py`

Verification:

```bash
bash scripts/test.sh tests/test_structure_validation.py -q
bash scripts/test.sh tests/test_structure_recognition.py -q
bash scripts/test.sh tests/test_document_extraction.py -q
bash scripts/test.sh tests/test_document_layout_cleanup.py -q
bash scripts/test.sh tests/test_document_structure_repair.py -q
bash scripts/test.sh tests/test_document_structure_blocks.py -q
```

### Step 8. Move Pipeline Family

Move all `document_pipeline*.py` modules as one atomic family.

Verification:

```bash
bash scripts/test.sh tests/test_document_pipeline.py -q
bash scripts/test.sh tests/test_document_pipeline_output_validation.py -q
bash scripts/test.sh tests/test_document_pipeline_failures.py -q
```

### Step 9. Move Image and Real Image Family

Move all `image_*.py` modules as one atomic family.

Move `real_image_manifest.py` to `src/docxaicorrector/real_image/manifest.py`.

Verification:

```bash
bash scripts/test.sh tests/test_image_analysis.py -q
bash scripts/test.sh tests/test_image_generation.py -q
bash scripts/test.sh tests/test_image_integration.py -q
bash scripts/test.sh tests/test_image_pipeline_policy.py -q
bash scripts/test.sh tests/test_image_prompts.py -q
bash scripts/test.sh tests/test_image_reconstruction.py -q
bash scripts/test.sh tests/test_image_reinsertion.py -q
bash scripts/test.sh tests/test_image_validation.py -q
bash scripts/test.sh tests/test_real_image_manifest.py -q
bash scripts/test.sh tests/test_real_image_pipeline.py -q
python -m docxaicorrector.real_image.manifest
```

### Step 10. Move Processing Family and State

Move:

- `preparation.py`
- `processing_runtime.py`
- `processing_service.py`
- `state.py`

`state.py` movement must update `tests/test_session_state_ownership.py` in the same batch. The test must use explicit path-based ownership for both the root wrapper and the package implementation path:

```python
OWNER_FILES = {
    PROJECT_ROOT / "state.py",
    PROJECT_ROOT / "src" / "docxaicorrector" / "runtime" / "state.py",
}
```

Do not keep a broad `path.name == "state.py"` skip once the package copy exists. Replace it with an explicit path-based skip using `OWNER_FILES`, not a broad directory skip.

Verification:

```bash
bash scripts/test.sh tests/test_preparation.py -q
bash scripts/test.sh tests/test_processing_runtime.py -q
bash scripts/test.sh tests/test_processing_service.py -q
bash scripts/test.sh tests/test_state.py -q
bash scripts/test.sh tests/test_session_state_ownership.py -q
python -c "import state; import docxaicorrector.runtime.state as target; assert state is target"
```

### Step 11. Move Generation Family

Move:

- `generation.py`
- `formatting_transfer.py`
- `formatting_diagnostics_retention.py`
- `message_formatting.py`
- `openai_response_utils.py`
- `search.py`

Verification:

```bash
bash scripts/test.sh tests/test_generation.py -q
bash scripts/test.sh tests/test_format_restoration.py -q
bash scripts/test.sh tests/test_message_formatting.py -q
bash scripts/test.sh tests/test_startup_performance_contract.py -q
python -c "import generation; import docxaicorrector.generation._generation as target; assert generation is target"
```

### Step 12. Move Validation Family and External Entry Points

Move:

- `real_document_validation_common.py`
- `real_document_validation_profiles.py`
- `real_document_validation_structural.py`

Update compatibility for script and benchmark entrypoints:

- Root `real_document_validation_structural.py` must use the Executable Compatibility Wrapper pattern, or `scripts/run-structural-preparation-diagnostic.sh` must be changed in the same batch to execute `python -m docxaicorrector.validation.structural`.
- `tests/artifacts/real_document_pipeline/run_lietaer_validation.py` must add `REPO_ROOT / "src"` to `sys.path` before `REPO_ROOT`, or be updated to package imports.
- `benchmark_projects/pdf_candidate_benchmark/benchmark_runner.py` must add `REPO_ROOT / "src"` to `sys.path` before `REPO_ROOT`, or be updated to package imports.
- `scripts/run_pic1_modes.py` must add `ROOT_DIR / "src"` to `sys.path` before `ROOT_DIR`, or be updated to package imports.
- `scripts/_run_cleanup_now.py` must either add `ROOT_DIR / "src"`/repo root bootstrap or be executed only through a wrapper that sets `PYTHONPATH` consistently.
- `scripts/_list_log_events.py` is source-scanning utility code, not a runtime import entrypoint. After migration its `TARGETS` list must be updated to scan package implementation paths, otherwise log-event inventory output will silently miss migrated modules.
- `real_image_manifest.py` has a CLI `main()` and `if __name__ == "__main__"` block. Its root wrapper must use the Executable Compatibility Wrapper pattern, or callers must use `python -m docxaicorrector.real_image.manifest`.

Verification:

```bash
bash scripts/test.sh tests/test_real_document_validation_profiles.py -q
bash scripts/test.sh tests/test_real_document_validation_corpus.py -q
bash scripts/test.sh tests/test_real_document_pipeline_validation.py -q
bash scripts/test.sh tests/test_real_document_structure_recognition_integration.py -q
bash scripts/run-structural-preparation-diagnostic.sh end-times-pdf-core --run-profile-id ui-parity-pdf-structural-recovery
python -m docxaicorrector.validation.structural end-times-pdf-core --run-profile-id ui-parity-pdf-structural-recovery
```

### Step 13. Move UI Family and Preserve Streamlit Entry Point

Move:

- `ui.py`
- `app_runtime.py`
- `application_flow.py`
- `compare_panel.py`
- `app.py` implementation to `src/docxaicorrector/ui/_app.py`

Root `app.py` becomes the split Streamlit/import wrapper shown in App Module Compatibility.

Verification:

```bash
bash scripts/test.sh tests/test_app.py -q
bash scripts/test.sh tests/test_app_runtime.py -q
bash scripts/test.sh tests/test_application_flow.py -q
bash scripts/test.sh tests/test_compare_panel.py -q
bash scripts/test.sh tests/test_ui.py -q
bash scripts/test.sh tests/test_startup_performance_contract.py -q
python -c "import app"
python -c "import app; import docxaicorrector.ui._app as target; assert app is target"
python -c "import app; assert hasattr(app, '_resolve_sidebar_settings'); assert hasattr(app, 'main')"
```

Smoke launch through the existing VS Code task or WSL terminal:

```bash
streamlit run app.py
```

### Step 14. Full Package Migration Verification

Run:

```bash
bash scripts/test.sh tests/ -q
bash scripts/test.sh tests/test_script_workflow_smoke.py -q
bash scripts/test.sh tests/test_startup_performance_contract.py -q
bash scripts/test.sh tests/test_session_state_ownership.py -q
bash scripts/test.sh tests/test_typecheck.py -q
bash scripts/run-real-document-validation.sh
bash scripts/run-real-document-quality-gate.sh
bash scripts/run-structural-preparation-diagnostic.sh end-times-pdf-core --run-profile-id ui-parity-pdf-structural-recovery
```

Every root production `.py` file should now be either:

- a module alias shim;
- the special `app.py` Streamlit entrypoint;
- an executable-compatible wrapper for a CLI entrypoint that forwards to package code.

### Step 15. Installable Package Formalization

Add `[project]`, `[project.optional-dependencies]`, and `[tool.setuptools.packages.find]` metadata to `pyproject.toml`.

Add or update CI/setup verification only if the project changes from `requirements.txt` installation to editable install.

Verification in WSL venv:

```bash
python -m pip install -e ".[dev]"
python -c "import docxaicorrector"
bash scripts/test.sh tests/test_typecheck.py -q
```

### Step 16. Optional Test Layout Migration

This step is optional and should be a separate PR.

If executed:

- Move non-protected tests to `tests/docxaicorrector/...`.
- Keep protected workflow/startup/session-state tests at root unless all callers are updated.
- Update `.github/CODEOWNERS`, `.github/workflows/ci.yml`, `.vscode/tasks.json`, and `tests/test_script_workflow_smoke.py` in the same batch.
- Verify full suite.

### Step 17. Deferred Monolith Decomposition

This step is explicitly deferred until package migration is complete and green.

Potential later decompositions:

- `src/docxaicorrector/core/models.py` to `src/docxaicorrector/core/models/` package.
- `src/docxaicorrector/core/config.py` to `src/docxaicorrector/core/config/` package.
- `src/docxaicorrector/ui/_app.py` into UI panel modules.
- `src/docxaicorrector/processing/processing_runtime.py` into runtime/upload/workers/draining modules.
- `PreparedRunContext` and `PreparedDocumentData` unification.

Each file-to-package replacement must be its own spec or PR because Python cannot have `models.py` and `models/` at the same level simultaneously. The replacement plan must include import identity checks and root alias updates.

## Acceptance Criteria

1. `src/docxaicorrector/` exists with package scaffolding, `__init__.py` files, and `py.typed`.
2. Every current root production module in the inventory table has a target implementation path.
3. Every migrated root module is an identity-preserving alias shim or a documented executable wrapper.
4. Root imports return the same module object as their package targets: `config is docxaicorrector.core.config`, `generation is docxaicorrector.generation._generation`, `preparation is docxaicorrector.processing.preparation`, `models is docxaicorrector.core.models`, `state is docxaicorrector.runtime.state`, and `app is docxaicorrector.ui._app` when imported normally.
5. `streamlit run app.py` launches without import errors.
6. `constants.BASE_DIR`, `CONFIG_PATH`, `PROMPTS_DIR`, `ENV_PATH`, `RUN_DIR`, and UI artifact paths resolve to the same repo-root locations as before migration.
7. Canonical WSL pytest path passes with baseline-equivalent counts:
   ```bash
   bash scripts/test.sh tests/ -q
   ```
8. Protected contract tests pass:
   ```bash
   bash scripts/test.sh tests/test_script_workflow_smoke.py -q
   bash scripts/test.sh tests/test_startup_performance_contract.py -q
   bash scripts/test.sh tests/test_session_state_ownership.py -q
   bash scripts/test.sh tests/test_typecheck.py -q
   ```
9. Real-document validation and quality gate pass with baseline-equivalent outcomes:
   ```bash
   bash scripts/run-real-document-validation.sh
   bash scripts/run-real-document-quality-gate.sh
   ```
10. Structural diagnostic CLI still works:
    ```bash
    bash scripts/run-structural-preparation-diagnostic.sh end-times-pdf-core --run-profile-id ui-parity-pdf-structural-recovery
    ```
11. Editable install succeeds after Phase 3:
    ```bash
    python -m pip install -e ".[dev]"
    python -c "import docxaicorrector"
    ```
12. `pyright` remains zero-error through the protected `tests/test_typecheck.py` contract.
13. No production behavior, log payload, event payload, artifact path, UI widget behavior, or pipeline output changes as a result of the structural move.
14. `.github/CODEOWNERS` protects the effective implementation paths for protected modules once they move under `src/docxaicorrector/`, not only their root compatibility wrappers.

## Final Verification Matrix

Run in the canonical WSL project runtime:

```bash
bash scripts/test.sh tests/ -q
bash scripts/test.sh tests/test_script_workflow_smoke.py -q
bash scripts/test.sh tests/test_startup_performance_contract.py -q
bash scripts/test.sh tests/test_session_state_ownership.py -q
bash scripts/test.sh tests/test_typecheck.py -q
bash scripts/run-real-document-validation.sh
bash scripts/run-real-document-quality-gate.sh
bash scripts/run-structural-preparation-diagnostic.sh end-times-pdf-core --run-profile-id ui-parity-pdf-structural-recovery
python -m pip install -e ".[dev]"
python -c "import docxaicorrector; import config; import docxaicorrector.core.config as target; assert config is target"
python -c "import generation; import docxaicorrector.generation._generation as target; assert generation is target"
python -c "from preparation import PreparedDocumentData as A; from docxaicorrector.processing.preparation import PreparedDocumentData as B; assert A is B"
```

Optional direct type checks after `tests/test_typecheck.py` passes:

```bash
pyright src/docxaicorrector
pyright tests
```

## Risks and Mitigations

### R-1. Root alias shims hide package import cycles

Mitigation: verify direct package imports for every moved module in the same batch, not only root imports.

### R-1a. Root aliases fail outside pytest or shell wrappers because `src` is not bootstrapped

Mitigation: require every root shim and executable wrapper to insert repository `src/` directly before importing `docxaicorrector`, and keep plain `python -c` compatibility checks in every affected verification batch.

### R-2. Startup regression from package re-exports

Mitigation: keep `__init__.py` lightweight and run `tests/test_startup_performance_contract.py` after core, generation, and UI batches.

### R-3. Path regression from moved constants

Mitigation: add path-resolution tests before moving `constants.py` and keep sentinel-based repo-root detection.

### R-4. Protected tests become stale after moving files

Mitigation: update protected tests in the same batch as the file they protect. Do not move protected tests during initial migration.

### R-4a. CODEOWNERS continues protecting only root wrappers after implementation moves under `src/`

Mitigation: whenever a CODEOWNERS-protected root production module moves, update `.github/CODEOWNERS` and the related smoke-test assertions in the same batch so protection follows the implementation path as well as the root wrapper.

### R-5. Real-document scripts miss `src` in `PYTHONPATH`

Mitigation: update all canonical scripts that activate the WSL venv, not just `scripts/test.sh`.

### R-6. File-to-package decomposition creates import conflicts

Mitigation: defer monolith decomposition until after package migration. Treat each file-to-package replacement as a separate spec/PR.

### R-7. CI and local setup drift between `requirements.txt` and `pyproject.toml`

Mitigation: keep `requirements.txt` as the CI/setup source until a dedicated dependency-management change updates CI, setup scripts, and workflow tests.

## Done Criteria

The safe architecture refactoring is complete when:

1. All implementation code from the inventory table lives under `src/docxaicorrector/`.
2. Root modules are compatibility aliases or documented executable wrappers only.
3. `streamlit run app.py` works.
4. All protected contracts pass.
5. Full pytest suite passes with baseline-equivalent counts.
6. Real-document validation and quality gate pass with baseline-equivalent outcomes.
7. Editable package install succeeds.
8. `docxaicorrector` is importable without relying on root production modules.
9. Root import backward compatibility remains intact.
10. Documentation and workflow references are synchronized after code migration.
