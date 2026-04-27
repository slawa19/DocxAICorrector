from typing import Any
from pathlib import Path

from config import load_app_config
from real_document_validation_common import build_validation_runtime_config
from real_document_validation_profiles import PROJECT_ROOT, apply_runtime_resolution_to_app_config, load_validation_registry, resolve_runtime_resolution


def test_load_validation_registry_reads_lietaer_profile() -> None:
    registry = load_validation_registry()

    document_profile = registry.get_document_profile("lietaer-core")
    run_profile = registry.get_run_profile("ui-parity-default")
    ai_run_profile = registry.get_run_profile("ui-parity-ai-default")

    assert document_profile.source_path == "tests/sources/Лиетар глава1.docx"
    assert document_profile.artifact_prefix == "lietaer_validation"
    assert document_profile.default_run_profile == "ui-parity-ai-default"
    assert document_profile.min_merged_groups == 1
    assert document_profile.min_merged_raw_paragraphs == 2
    assert "headings" in document_profile.tags
    assert run_profile.tier == "full"
    assert run_profile.enable_paragraph_markers is True
    assert ai_run_profile.structure_recognition_mode == "always"
    assert ai_run_profile.structure_recognition_enabled is None


def test_resolve_runtime_resolution_reports_explicit_overrides() -> None:
    registry = load_validation_registry()
    app_config = load_app_config()
    run_profile = registry.get_run_profile("ui-parity-ai-default")

    resolution = resolve_runtime_resolution(app_config, run_profile)

    assert resolution.effective.enable_paragraph_markers is True
    assert resolution.effective.structure_recognition_mode == "always"
    assert resolution.effective.structure_recognition_enabled is True
    assert resolution.effective.processing_operation == app_config.processing_operation_default
    assert resolution.effective.translation_domain == app_config.translation_domain_default
    assert resolution.effective.audiobook_postprocess_enabled is app_config.audiobook_postprocess_default
    assert resolution.ui_defaults.structure_recognition_mode == "auto"
    assert resolution.ui_defaults.model == app_config.models.text.default
    assert resolution.overrides["enable_paragraph_markers"] is True
    assert resolution.overrides["structure_recognition_mode"] == "always"


def test_document_profile_resolves_source_path_inside_workspace() -> None:
    registry = load_validation_registry()
    document_profile = registry.get_document_profile("lietaer-core")

    resolved_path = document_profile.resolved_source_path(PROJECT_ROOT)

    assert isinstance(resolved_path, Path)
    assert str(resolved_path).replace("\\", "/").endswith("tests/sources/Лиетар глава1.docx")


def test_build_validation_runtime_config_keeps_canonical_nested_shape() -> None:
    registry = load_validation_registry()
    app_config = load_app_config()
    run_profile = registry.get_run_profile("ui-parity-ai-default")

    runtime_config: dict[str, Any] = build_validation_runtime_config(resolve_runtime_resolution(app_config, run_profile))  # type: ignore[assignment]

    assert set(runtime_config.keys()) == {"effective", "ui_defaults", "overrides"}
    assert runtime_config["effective"]["image_mode"] == runtime_config["ui_defaults"]["image_mode"]
    assert runtime_config["overrides"]["enable_paragraph_markers"] is True
    assert runtime_config["effective"]["structure_recognition_mode"] == "always"
    assert runtime_config["effective"]["structure_recognition_enabled"] is True
    assert runtime_config["overrides"]["structure_recognition_mode"] == "always"
    assert runtime_config["effective"]["translation_domain"] == runtime_config["ui_defaults"]["translation_domain"]


def test_load_validation_registry_reads_second_corpus_profile_and_soak_run_profile() -> None:
    registry = load_validation_registry()

    document_profile = registry.get_document_profile("religion-wealth-core")
    run_profile = registry.get_run_profile("ui-parity-soak-3x")
    structural_run_profile = registry.get_run_profile("structural-passthrough-default")

    assert document_profile.source_path == "tests/sources/Собственность и богатство в религиях.doc"
    assert document_profile.structural_mode == "tolerant"
    assert document_profile.max_formatting_diagnostics == 1
    assert "legacy-doc" in document_profile.tags
    assert run_profile.mode == "soak"
    assert run_profile.repeat_count == 3
    assert run_profile.tier == "full"
    assert structural_run_profile.tier == "structural"
    assert structural_run_profile.structure_recognition_mode == "off"


def test_load_validation_registry_reads_mazzucato_audiobook_profile_and_run_profile() -> None:
    registry = load_validation_registry()

    document_profile = registry.get_document_profile("mazzucato-audiobook-core")
    run_profile = registry.get_run_profile("ui-parity-translate-audiobook-postprocess")
    baseline_run_profile = registry.get_run_profile("ui-parity-translate-baseline")

    assert document_profile.default_run_profile == "ui-parity-translate-audiobook-postprocess"
    assert document_profile.source_path.endswith("Mariana Mazzucato (z-lib.org).docx")
    assert "audiobook" in document_profile.tags
    assert run_profile.tier == "full"
    assert run_profile.enable_paragraph_markers is True
    assert run_profile.repeat_count == 1
    assert run_profile.processing_operation == "translate"
    assert run_profile.audiobook_postprocess_enabled is True
    assert baseline_run_profile.processing_operation == "translate"
    assert baseline_run_profile.audiobook_postprocess_enabled is False


def test_load_validation_registry_reads_end_times_pdf_profile_and_theology_run_profile() -> None:
    registry = load_validation_registry()

    document_profile = registry.get_document_profile("end-times-pdf-core")
    run_profile = registry.get_run_profile("ui-parity-translate-theology-pdf-high-quality")

    assert document_profile.source_path == "tests/sources/Are_We_In_The_End_Times.pdf"
    assert document_profile.require_toc_detected is True
    assert document_profile.require_pdf_conversion is True
    assert document_profile.require_no_bullet_headings is True
    assert document_profile.require_no_toc_body_concat is True
    assert document_profile.require_translation_domain == "theology"
    assert document_profile.structural_run_profile == "ui-parity-translate-theology-pdf-high-quality"
    assert document_profile.structural_expected_result == "fail"
    assert document_profile.structural_expected_failed_checks == (
        "unmapped_source_threshold",
        "unmapped_target_threshold",
    )
    assert document_profile.default_run_profile == "ui-parity-translate-theology-pdf-high-quality"
    assert run_profile.processing_operation == "translate"
    assert run_profile.translation_domain == "theology"
    assert run_profile.structure_recognition_mode == "always"


def test_apply_runtime_resolution_maps_translation_domain_to_pipeline_config() -> None:
    registry = load_validation_registry()
    app_config = load_app_config()
    run_profile = registry.get_run_profile("ui-parity-translate-theology-pdf-high-quality")

    runtime_config = apply_runtime_resolution_to_app_config(app_config, resolve_runtime_resolution(app_config, run_profile))

    assert runtime_config["translation_domain"] == "theology"
    assert runtime_config["translation_domain_default"] == "theology"
