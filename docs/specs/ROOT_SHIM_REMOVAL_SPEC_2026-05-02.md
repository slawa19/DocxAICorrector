# Root Shim Removal Specification

Date: 2026-05-02

Status: planned; awaiting approval.

## Goal

Remove all root-level compatibility shim files (`.py` + `.pyi`) from the project root, except
the Streamlit entrypoint `app.py` and its typing stub `app.pyi`.

This eliminates ~130 files from the repository root and makes `src/docxaicorrector/` the single
canonical location for all production code.

## Background

The safe architecture refactoring (completed 2026-04-29) moved all production code into
`src/docxaicorrector/` and kept thin root shims as backward-compatibility layer:

```python
# Example shim (config.py)
from importlib import import_module
from pathlib import Path, sys
_SRC = Path(__file__).resolve().parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))
_target = import_module("docxaicorrector.core.config")
sys.modules[__name__] = _target
```

A usage audit (2026-05-02) confirmed:

- `src/docxaicorrector/` — **0 root imports** (clean, all use `docxaicorrector.*`)
- `scripts/` — **0 root imports** (all use `docxaicorrector.*`)
- `benchmark_projects/` — **0 root imports** (all use `docxaicorrector.*`)
- `tests/` + `conftest.py` — **42 test files + 1 conftest** use root shim imports

Root shims are only needed to support test-file imports. Because the shims do
`sys.modules[__name__] = _target`, `import config` and `import docxaicorrector.core.config` already
return **the same module object**. The migration is therefore purely mechanical: swap import
statements, keep all downstream usage unchanged.

## Scope

Files to **remove** after test migration is complete:

- Every `<module>.py` root shim (all files listed in the Module Map below)
- Every `<module>.pyi` root stub alongside its removed shim

Files that **remain** (not in scope for removal):

- `app.py` — Streamlit entrypoint; stays, but converted from shim to minimal direct wrapper
- `app.pyi` — stays alongside `app.py`

## Non-Goals

- No changes to `src/docxaicorrector/` production code
- No changes to pipeline logic, UI behavior, event payloads, or quality gates
- No changes to `scripts/`, `benchmark_projects/`, or `.github/workflows/ci.yml`
  (they already use `docxaicorrector.*` imports)
- No changes to the real-document validation or quality-gate contracts
- No test coverage changes — tests keep asserting the same behavior, only import paths change

## Migration Pattern

The key insight: every `import <root_module>` becomes
`import docxaicorrector.<subpackage>.<module> as <root_module>`.

The alias suffix preserves all downstream references (`config.CONFIG_PATH`,
`monkeypatch.setattr(config, ...)`, `from config import X`, etc.) without any changes beyond the
import line itself.

```python
# Before
import config
import generation
from models import ParagraphUnit

# After
import docxaicorrector.core.config as config
import docxaicorrector.generation._generation as generation
from docxaicorrector.core.models import ParagraphUnit
```

For `from <root_module> import X` style, keep the explicit import form:

```python
# Before
from config import ModelRegistry, TextModelConfig

# After
from docxaicorrector.core.config import ModelRegistry, TextModelConfig
```

`monkeypatch.setattr(config, "CONFIG_PATH", ...)` requires **no change** after swapping the import,
because `config` is now the actual module object, not a shim over it.

## Module Map

Full mapping of root shim → canonical package path:

| Root shim | Package target |
|---|---|
| `application_flow.py` | `docxaicorrector.ui.application_flow` |
| `app_runtime.py` | `docxaicorrector.ui.app_runtime` |
| `compare_panel.py` | `docxaicorrector.ui.compare_panel` |
| `recommended_text_settings.py` | `docxaicorrector.ui.recommended_text_settings` |
| `ui.py` | `docxaicorrector.ui._ui` |
| `config.py` | `docxaicorrector.core.config` |
| `config_loader_layers.py` | `docxaicorrector.core.config_loader_layers` |
| `config_model_registry.py` | `docxaicorrector.core.config_model_registry` |
| `config_runtime_sections.py` | `docxaicorrector.core.config_runtime_sections` |
| `config_structure_sections.py` | `docxaicorrector.core.config_structure_sections` |
| `constants.py` | `docxaicorrector.core.constants` |
| `logger.py` | `docxaicorrector.core.logger` |
| `models.py` | `docxaicorrector.core.models` |
| `document.py` | `docxaicorrector.document._document` |
| `document_boundaries.py` | `docxaicorrector.document.boundaries` |
| `document_boundary_review.py` | `docxaicorrector.document.boundary_review` |
| `document_extraction.py` | `docxaicorrector.document.extraction` |
| `document_layout_cleanup.py` | `docxaicorrector.document.layout_cleanup` |
| `document_relations.py` | `docxaicorrector.document.relations` |
| `document_roles.py` | `docxaicorrector.document.roles` |
| `document_semantic_blocks.py` | `docxaicorrector.document.semantic_blocks` |
| `document_shared_xml.py` | `docxaicorrector.document.shared_xml` |
| `document_structure_repair.py` | `docxaicorrector.document.structure_repair` |
| `document_tables.py` | `docxaicorrector.document.tables` |
| `document_pipeline.py` | `docxaicorrector.pipeline._pipeline` |
| `document_pipeline_block_execution.py` | `docxaicorrector.pipeline.block_execution` |
| `document_pipeline_block_failures.py` | `docxaicorrector.pipeline.block_failures` |
| `document_pipeline_contracts.py` | `docxaicorrector.pipeline.contracts` |
| `document_pipeline_job_parsing.py` | `docxaicorrector.pipeline.job_parsing` |
| `document_pipeline_late_phases.py` | `docxaicorrector.pipeline.late_phases` |
| `document_pipeline_output_validation.py` | `docxaicorrector.pipeline.output_validation` |
| `document_pipeline_setup.py` | `docxaicorrector.pipeline.setup` |
| `document_pipeline_support.py` | `docxaicorrector.pipeline.support` |
| `generation.py` | `docxaicorrector.generation._generation` |
| `formatting_diagnostics_retention.py` | `docxaicorrector.generation.formatting_diagnostics_retention` |
| `formatting_transfer.py` | `docxaicorrector.generation.formatting_transfer` |
| `message_formatting.py` | `docxaicorrector.generation.message_formatting` |
| `openai_response_utils.py` | `docxaicorrector.generation.openai_response_utils` |
| `search.py` | `docxaicorrector.generation.search` |
| `image_analysis.py` | `docxaicorrector.image.analysis` |
| `image_generation.py` | `docxaicorrector.image.generation` |
| `image_output_policy.py` | `docxaicorrector.image.output_policy` |
| `image_pipeline.py` | `docxaicorrector.image.pipeline` |
| `image_pipeline_policy.py` | `docxaicorrector.image.pipeline_policy` |
| `image_prompts.py` | `docxaicorrector.image.prompts` |
| `image_reconstruction.py` | `docxaicorrector.image.reconstruction` |
| `image_reinsertion.py` | `docxaicorrector.image.reinsertion` |
| `image_shared.py` | `docxaicorrector.image.shared` |
| `image_validation.py` | `docxaicorrector.image.validation` |
| `real_image_manifest.py` | `docxaicorrector.real_image.manifest` |
| `structure_recognition.py` | `docxaicorrector.structure.recognition` |
| `structure_validation.py` | `docxaicorrector.structure.validation` |
| `preparation.py` | `docxaicorrector.processing.preparation` |
| `processing_runtime.py` | `docxaicorrector.processing.processing_runtime` |
| `processing_service.py` | `docxaicorrector.processing.processing_service` |
| `restart_store.py` | `docxaicorrector.processing.restart_store` |
| `runtime_artifact_retention.py` | `docxaicorrector.runtime.artifact_retention` |
| `runtime_artifacts.py` | `docxaicorrector.runtime.artifacts` |
| `runtime_events.py` | `docxaicorrector.runtime.events` |
| `state.py` | `docxaicorrector.runtime.state` |
| `workflow_state.py` | `docxaicorrector.runtime.workflow_state` |
| `real_document_validation_common.py` | `docxaicorrector.validation.common` |
| `real_document_validation_profiles.py` | `docxaicorrector.validation.profiles` |
| `real_document_validation_structural.py` | `docxaicorrector.validation.structural` |
| `text_transform_assessment.py` | `docxaicorrector.text.transform_assessment` |
| `translation_domains.py` | `docxaicorrector.text.translation_domains` |

## `app.py` Special Case

`app.py` stays in the root as the Streamlit entrypoint. After all tests migrate their
`import app` to `import docxaicorrector.ui._app as app`, the `sys.modules` shim pattern can be
removed from `app.py`. The file becomes a minimal direct launcher:

```python
"""Streamlit entrypoint for DocxAICorrector."""
from pathlib import Path
import sys

_SRC = Path(__file__).resolve().parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from docxaicorrector.ui._app import main

if __name__ == "__main__":
    main()
```

`app.pyi` stays and continues to reflect `docxaicorrector.ui._app` public surface.

## Collateral File Changes

### `tests/conftest.py`

- Replace `from config import ModelRegistry, TextModelConfig`
  → `from docxaicorrector.core.config import ModelRegistry, TextModelConfig`
- Remove the `_ensure_src_first_import_order` call that adds `PROJECT_ROOT` to `sys.path`.
  Only `SRC_ROOT` is needed after root shims are gone.

### `tests/test_root_typing_stubs.py`

- `test_each_root_typing_stub_has_matching_root_python_module` — remove or update to enumerate
  only `app.pyi` (the sole remaining stub).
- `test_root_typing_stub_targets_match_root_module_contract` — keep for `app.pyi` only.

### `tests/test_script_workflow_smoke.py` (CODEOWNERS-protected)

- The test that checks `_ensure_src_first_import_order` in `conftest.py` and bootstrap entrypoints
  must be updated to reflect that `PROJECT_ROOT` is no longer added to `sys.path` in `conftest.py`.

### `.github/CODEOWNERS`

Remove all root shim entries after their files are deleted. Only keep:

```
/app.py @slawa19
/app.pyi @slawa19
/src/docxaicorrector/ui/_app.py @slawa19
# ... (package implementation entries remain unchanged)
```

## Execution Plan

### Baseline

```bash
bash scripts/test.sh tests/ -q
```

Record pass/fail counts. All tests must be green before starting.

### Step 1. Migrate `tests/conftest.py`

Replace root import of `config` with `docxaicorrector.core.config`.
Remove `PROJECT_ROOT` from `_ensure_src_first_import_order` call.

Verify:

```bash
bash scripts/test.sh tests/ -q
```

### Step 2. Migrate tests by module group

Work through test files in groups. Each group: update imports, run tests, verify green.

Recommended groups:

**Group A — core** (config, constants, models, logger, state):
- `test_config.py`
- `test_logger.py`
- `test_state.py`
- `test_startup_performance_contract.py` ← CODEOWNERS-protected, update in this batch

**Group B — UI** (app, ui, application_flow, compare_panel, app_runtime, recommended_text_settings):
- `test_app.py` ← CODEOWNERS-protected
- `test_ui.py`
- `test_application_flow.py`
- `test_compare_panel.py`
- `test_app_runtime.py`
- `test_app_preparation.py`
- `test_app_recommendations.py`
- `test_app_restartable_state.py`

**Group C — document** (document, extraction, layout_cleanup, boundary_review, structure_repair):
- `test_document_extraction.py`
- `test_document_layout_cleanup.py`
- `test_document_structure_blocks.py`
- `test_document_structure_repair.py`
- `test_paragraph_boundary_normalization.py`
- `test_format_restoration.py`

**Group D — pipeline** (document_pipeline and variants):
- `test_document_pipeline.py`
- `test_document_pipeline_failures.py`
- `test_document_pipeline_output_validation.py`

**Group E — generation** (generation, formatting, message_formatting, search):
- `test_generation.py`
- `test_narration_markdown.py`
- `test_message_formatting.py`
- `test_format_restoration.py` (if not covered in Group C)

**Group F — image** (image_*):
- `test_image_analysis.py`
- `test_image_generation.py`
- `test_image_integration.py`
- `test_image_pipeline_compare_helpers.py`
- `test_image_pipeline_policy.py`
- `test_image_prompts.py`
- `test_image_reconstruction.py`
- `test_image_reinsertion.py`
- `test_image_validation.py`
- `test_real_image_manifest.py`
- `test_real_image_pipeline.py`

**Group G — processing** (preparation, processing_runtime, processing_service, restart_store):
- `test_preparation.py`
- `test_processing_runtime.py`
- `test_processing_service.py`
- `test_restart_store.py`

**Group H — runtime** (runtime_artifacts, runtime_artifact_retention, workflow_state):
- `test_app_runtime.py` (if not covered in Group B)
- `test_runtime_artifacts.py`
- `test_runtime_artifact_retention.py`
- `test_workflow_state.py`

**Group I — structure and text** (structure_recognition, structure_validation, text_transform_assessment, translation_domains):
- `test_structure_recognition.py`
- `test_structure_validation.py`
- `test_text_transform_assessment.py`
- `test_translation_domains.py`

**Group J — validation** (real_document_validation_*):
- `test_real_document_validation_profiles.py`
- `test_real_document_pipeline_validation.py`
- `test_real_document_structure_recognition_integration.py`
- `test_real_document_validation_corpus.py`

After each group:

```bash
bash scripts/test.sh tests/ -q
```

### Step 3. Update `test_root_typing_stubs.py` and `test_script_workflow_smoke.py`

- Update `test_root_typing_stubs.py` to cover only `app.pyi`.
- Update the bootstrap assertion in `test_script_workflow_smoke.py` to reflect the
  simplified `conftest.py` path-bootstrap behavior.

Verify:

```bash
bash scripts/test.sh tests/test_script_workflow_smoke.py -q
bash scripts/test.sh tests/test_root_typing_stubs.py -q
```

### Step 4. Simplify `app.py`

Convert `app.py` from shim to minimal direct Streamlit launcher (see `app.py` Special Case above).

Verify:

```bash
bash scripts/test.sh tests/test_script_workflow_smoke.py -q
bash scripts/test.sh tests/test_startup_performance_contract.py -q
```

### Step 5. Delete root shim files

For each module in the Module Map: delete `<module>.py` and `<module>.pyi`.

Deletions must happen in one batch per module group so partial deletion states are not committed.

Verify after each group deletion:

```bash
bash scripts/test.sh tests/ -q
```

### Step 6. Update `CODEOWNERS`

Remove all entries referencing deleted root shim files.

Verify:

```bash
bash scripts/test.sh tests/test_script_workflow_smoke.py -q
bash scripts/test.sh tests/ -q
```

## Final Verification

```bash
bash scripts/test.sh tests/ -q
bash scripts/test.sh tests/test_script_workflow_smoke.py -q
bash scripts/test.sh tests/test_startup_performance_contract.py -q
bash scripts/test.sh tests/test_typecheck.py -q
bash scripts/run-real-document-validation.sh
bash scripts/run-real-document-quality-gate.sh
```

All must pass with the same counts as the baseline.

## Done Criteria

1. No `.py` or `.pyi` root shim files remain except `app.py` and `app.pyi`.
2. All test files import directly from `docxaicorrector.*` package paths.
3. `conftest.py` does not add `PROJECT_ROOT` to `sys.path`.
4. `app.py` does not use `sys.modules[__name__] = _target` shim pattern.
5. `CODEOWNERS` contains no entries for deleted root files.
6. Full test suite passes with the same test counts as the baseline.
7. Typecheck (`test_typecheck.py`) remains green.
8. Real-document validation and quality gate pass.

## Risk Notes

- `test_startup_performance_contract.py` and `test_app.py` are CODEOWNERS-protected. Their import
  changes are mechanical but must be done carefully to preserve monkeypatching semantics.
- `test_script_workflow_smoke.py` is CODEOWNERS-protected and checks bootstrap assumptions in
  `conftest.py`. Step 1 and Step 3 must update it in sync.
- The `ROOT_COMPATIBILITY_TYPING_SURFACE_SPEC_2026-05-01.md` follow-up (tightening `.pyi` stubs)
  becomes moot for all deleted files. It only remains relevant for `app.pyi`.
