# Feature Specification: Break the processing → ui import cycle

Date: 2026-07-15
Status: **PLANNED (Wave 2 / S5).** Structural refactor. Move the domain preparation contract and its orchestration
out of the ui layer so the processing core imports without Streamlit/ui. Behaviour-preserving.
Owner surface: new `processing/application_flow.py`; slimmed `ui/application_flow.py` (re-export + UI/state helpers);
`processing/processing_service.py`; `runtime/state.py`; relocated i18n (`core/i18n.py` + `core/locales/`, shim at
`ui/i18n.py`).
Companion: prerequisite for the planned FastAPI backend/worker split (`plans/monetization*.md`) — a backend must
import the processing core without the ui package.

## Problem (verified against HEAD d27c137)

`PreparedRunContext` — a domain preparation contract — and its orchestration live in the ui layer
([ui/application_flow.py:59](/D:/www/Projects/2025/DocxAICorrector/src/docxaicorrector/ui/application_flow.py#L59)),
and the processing/runtime layers import UP into ui to reach them:

- `processing/processing_service.py:55` `import docxaicorrector.ui.application_flow` (uses `PreparedRunContext`,
  `prepare_run_context_for_background`, and re-exported `prepare_document_for_processing`).
- `runtime/state.py:12,284` import `PreparedRunContext` from `ui.application_flow`.

`ui.application_flow` in turn imports `processing.preparation`, `processing.processing_runtime`,
`processing.restart_store`, `runtime.state`, and `ui.i18n` — a processing↔ui package cycle. It makes the core
unusable without the ui package and blocks a headless backend/worker.

## Scope (planned)

1. **New `processing/application_flow.py`** holds the domain contract + preparation orchestration (no ui import):
   `PreparedRunContext`, `NormalizationMetrics`, the `flatten_*` metric helpers, `ResolvedPreparationUpload`,
   `_resolve_preparation_upload`, `_resolve_preparation_dependencies`, `_prepare_run_context_core`,
   `_raise_or_fail_preparation`, `_build_quality_gate_blocked_message`, `_build_quality_gate_warning_message`,
   `_build_prepared_run_context`, `prepare_run_context_for_background`.
2. **Relocate i18n to a neutral layer** so the moved code can localize without importing ui: move `ui/i18n.py` →
   `core/i18n.py` and `ui/locales/` → `core/locales/`; leave a thin re-export shim at `ui/i18n.py` so the genuine
   UI callers (`ui/_app.py`, `ui/_ui.py`, `ui/review_presentation.py`, tests) are unchanged. The moved orchestration
   imports `from docxaicorrector.core.i18n import t` (same catalog → identical messages).
3. **Slim `ui/application_flow.py`** to the UI/state helpers (`sync_selected_file_context`, `get_cached_*_file`,
   `should_log_document_prepared`, `consume_completed_source_if_used`, `has_restartable_source`,
   `has_resettable_state`, `resolve_effective_uploaded_file`, `derive_app_idle_view_state`, and the session-state
   `prepare_run_context` entrypoint) and **re-export** the moved symbols from `processing.application_flow` so every
   existing `docxaicorrector.ui.application_flow.X` reference (ui/_ui, ui/_app, tests) keeps working. `ui → processing`
   is the allowed direction.
4. **Repoint the upward importers**: `processing_service.py` imports `PreparedRunContext` +
   `prepare_run_context_for_background` from `processing.application_flow` and `prepare_document_for_processing`
   from `processing.preparation`; `runtime/state.py` imports `PreparedRunContext` from `processing.application_flow`.
   Remove `import docxaicorrector.ui.application_flow` from both.

No new DI framework; no pipeline rewrite. The existing dependency-injection seams (fn params) are reused.

## Test plan

- New guard test: no module under `processing/`, `runtime/`, `generation/`, `pipeline/`, `validation/`,
  `document/`, `image/` imports `docxaicorrector.ui` (static AST/import scan) — pins the layering so the cycle
  cannot reappear.
- Import test: `import docxaicorrector.processing.processing_service` and
  `import docxaicorrector.processing.application_flow` succeed without importing the `ui` package (assert
  `docxaicorrector.ui` absent from `sys.modules`, or that ui submodules aren't pulled).
- Behaviour: existing `tests/test_application_flow.py`, `test_app_preparation.py`, `test_processing_service.py`,
  `test_state.py`, and i18n tests stay green (re-exports + shim preserve the public surface and messages).

## Out of scope

- Splitting the ui `prepare_run_context` session-state entrypoint further, or extracting a formal service interface.
- Any change to preparation logic, quality-gate semantics, or message catalogs (byte-identical strings).

## SaaS rationale

The FastAPI backend/worker must import the processing core (preparation, jobs, `PreparedRunContext`) without the
Streamlit ui package on the path. This removes the last structural blocker to that split.
