# Test Tier Inventory

Date: 2026-05-11
Status: provisional Phase 0 inventory
Scope: every top-level `tests/test_*.py` file currently in the repository gets one primary tier assignment.

This inventory is intentionally pragmatic:

- primary tier means the main signal the file is expected to provide today;
- some files are mixed and also contain secondary opt-in or compatibility coverage;
- browser UI remains an explicit gap rather than being implied by mocked Streamlit tests.

## Unit-Contract

- `tests/test_app.py`
- `tests/test_app_preparation.py`
- `tests/test_app_recommendations.py`
- `tests/test_app_restartable_state.py`
- `tests/test_app_runtime.py`
- `tests/test_application_flow.py`
- `tests/test_config.py`
- `tests/test_docxaicorrector_bootstrap_package.py`
- `tests/test_document_extraction.py`
- `tests/test_document_layout_cleanup.py`
- `tests/test_document_pipeline.py`
- `tests/test_document_pipeline_failures.py`
- `tests/test_document_pipeline_output_validation.py`
- `tests/test_document_structure_blocks.py`
- `tests/test_document_structure_repair.py`
- `tests/test_format_restoration.py`
- `tests/test_gate_detectors_stage2.py`
- `tests/test_generation.py`
- `tests/test_image_analysis.py`
- `tests/test_image_generation.py`
- `tests/test_image_pipeline_compare_helpers.py`
- `tests/test_image_pipeline_policy.py`
- `tests/test_image_prompts.py`
- `tests/test_image_reconstruction.py`
- `tests/test_image_reinsertion.py`
- `tests/test_image_validation.py`
- `tests/test_logger.py`
- `tests/test_message_formatting.py`
- `tests/test_model_registry_sweep.py`
- `tests/test_narration_markdown.py`
- `tests/test_output_display_hygiene.py`
- `tests/test_paragraph_boundary_normalization.py`
- `tests/test_passthrough_unmapped_acceptance.py`
- `tests/test_pdf_text_layer_logical_import.py`
- `tests/test_pdf_text_layer_quality.py`
- `tests/test_preparation.py`
- `tests/test_processing_runtime.py`
- `tests/test_processing_service.py`
- `tests/test_reader_cleanup_mvp.py`
- `tests/test_reader_cleanup_structural_matrix.py`
- `tests/test_recommended_text_settings.py`
- `tests/test_restart_store.py`
- `tests/test_root_typing_stubs.py`
- `tests/test_runtime_artifact_retention.py`
- `tests/test_runtime_artifacts.py`
- `tests/test_session_state_ownership.py`
- `tests/test_spec_image_followup.py`
- `tests/test_spec_image_level1.py`
- `tests/test_startup_performance_contract.py`
- `tests/test_state.py`
- `tests/test_structure_layout_signals.py`
- `tests/test_structure_review_panel.py`
- `tests/test_structure_validation.py`
- `tests/test_text_transform_assessment.py`
- `tests/test_translation_domains.py`
- `tests/test_validation_formatting_replay.py`
- `tests/test_ui.py`
- `tests/test_ui_i18n.py`
- `tests/test_ui_review_presentation.py`
- `tests/test_workflow_state.py`

## Compat-Legacy

- `tests/test_compare_panel.py`
- `tests/test_root_shim_identity_aliases.py`

## Static-Workflow

- `tests/test_script_contract_static.py`
- `tests/test_script_log_retention.py`

## Typecheck

- `tests/test_typecheck.py`

## Integration-Local

- `tests/test_image_integration.py`
- `tests/test_pdf_candidate_benchmark_project.py`
- `tests/test_pdf_import_backend_comparison.py`
- `tests/test_real_document_pipeline_validation.py`
- `tests/test_real_image_manifest.py`
- `tests/test_real_image_pipeline.py`
- `tests/test_script_workflow_smoke.py`
- `tests/test_structure_recognition_benchmark_runner.py`

## System-Deps

- `tests/test_real_document_validation_corpus.py`

## Manual-AI-Heavy

- no top-level manual-AI-heavy test file exists yet

## Browser-UI

- no top-level browser-backed test file exists yet

## Mixed-Surface Notes

- `tests/test_app.py` is primarily `unit-contract`, but it also contains explicit legacy tuple compatibility guards.
- `tests/test_generation.py` is primarily `unit-contract`, but it includes capability-sensitive subtests gated on Pandoc availability.
- `tests/test_real_document_validation_corpus.py` is primarily `system-deps`, but it already contains schema and runtime-resolution coverage that Phase 2 can split out if needed.
- `tests/test_real_image_pipeline.py` is primarily `integration-local`, but its live API smoke subtests belong to the `manual-ai-heavy` and `live-image-api` opt-in slice.
- `tests/test_script_workflow_smoke.py` now holds only env-sensitive subprocess/PowerShell/WSL/process smoke.