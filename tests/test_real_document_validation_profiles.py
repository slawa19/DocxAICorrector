from typing import Any
from pathlib import Path

from config import load_app_config
from real_document_validation_common import build_validation_runtime_config
from real_document_validation_profiles import PROJECT_ROOT, load_validation_registry, resolve_runtime_resolution


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
