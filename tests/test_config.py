import os
import threading
from pathlib import Path
from typing import cast

import pytest

import docxaicorrector.core.config as config
import docxaicorrector.core.constants as constants
from tests.conftest import (
    TEST_IMAGE_ANALYSIS_MODEL,
    TEST_IMAGE_EDIT_MODEL,
    TEST_IMAGE_GENERATION_MODEL,
    TEST_IMAGE_GENERATION_VISION_MODEL,
    TEST_IMAGE_RECONSTRUCTION_MODEL,
    TEST_IMAGE_VALIDATION_MODEL,
    TEST_STRUCTURE_RECOGNITION_MODEL,
    TEST_TEXT_MODEL_DEFAULT,
)


def test_constants_paths_resolve_to_repo_root() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    resources = repo_root / "src" / "docxaicorrector" / "resources"

    # Working root (writable) stays at the repo root in a checkout.
    assert constants.BASE_DIR == repo_root
    # Read-only resources are packaged (spec 025 / A2), not at the repo root.
    assert constants.RESOURCE_ROOT == resources
    assert constants.CONFIG_PATH == resources / "config.toml"
    assert constants.PROMPTS_DIR == resources / "prompts"
    assert constants.ENV_PATH == repo_root / ".env"
    assert constants.RUN_DIR == repo_root / ".run"
    assert constants.UI_RESULT_ARTIFACTS_DIR == repo_root / ".run" / "ui_results"
    assert constants.APP_LOG_PATH == repo_root / ".run" / "app.log"
    assert constants.APP_READY_PATH == repo_root / ".run" / "app.ready"


def test_load_app_config_applies_env_overrides_and_clamps(monkeypatch):
    monkeypatch.setattr(config, "CONFIG_PATH", config.CONFIG_PATH.parent / "__missing_config__.toml")
    monkeypatch.setenv("DOCX_AI_MODEL_OPTIONS", "gpt-5.4, custom-model")
    monkeypatch.setenv("DOCX_AI_DEFAULT_MODEL", "gpt-5.1")
    monkeypatch.setenv("DOCX_AI_CHUNK_SIZE", "20000")
    monkeypatch.setenv("DOCX_AI_MAX_RETRIES", "0")

    app_config = config.load_app_config()
    models = cast(config.ModelRegistry, app_config["models"])

    assert app_config["default_model"] == "gpt-5.1"
    assert app_config["model_options"] == ["gpt-5.1", "gpt-5.4", "custom-model"]
    assert models.text.default == "gpt-5.1"
    assert models.text.options == ("gpt-5.1", "gpt-5.4", "custom-model")
    assert app_config["chunk_size"] == 12000
    assert app_config["max_retries"] == 1
    assert app_config["processing_operation_default"] == "edit"
    assert app_config["source_language_default"] == "en"
    assert app_config["target_language_default"] == "ru"
    assert app_config["editorial_intensity_default"] == "literary"
    assert app_config["translation_domain_default"] == "general"
    supported_languages = cast(list[config.LanguageOption], app_config["supported_languages"])
    assert supported_languages[0].code == "ru"
    assert app_config["enable_paragraph_markers"] is False
    assert app_config["paragraph_boundary_normalization_enabled"] is True
    assert app_config["paragraph_boundary_normalization_mode"] == "high_only"
    assert app_config["paragraph_boundary_normalization_save_debug_artifacts"] is True
    assert models.structure_recognition == app_config["default_model"]
    assert app_config["structure_validation_enabled"] is True
    assert app_config["structure_validation_min_paragraphs_for_auto_gate"] == 40
    assert app_config["structure_validation_min_explicit_heading_density"] == 0.003
    assert app_config["structure_validation_max_suspicious_short_body_ratio_without_escalation"] == 0.05
    assert app_config["structure_validation_max_all_caps_or_centered_body_ratio_without_escalation"] == 0.03
    assert app_config["structure_validation_toc_like_sequence_min_length"] == 4
    assert app_config["structure_validation_forbid_heading_only_collapse"] is True
    assert app_config["structure_validation_save_debug_artifacts"] is True
    assert app_config["structure_validation_block_on_high_risk_noop"] is True
    assert app_config["relation_normalization_enabled"] is True
    assert app_config["relation_normalization_profile"] == "phase2_default"
    assert app_config["relation_normalization_enabled_relation_kinds"] == (
        "image_caption",
        "table_caption",
        "epigraph_attribution",
        "toc_region",
    )
    assert app_config["relation_normalization_save_debug_artifacts"] is True
    assert app_config["layout_artifact_cleanup_enabled"] is True
    assert app_config["layout_artifact_cleanup_min_repeat_count"] == 3
    assert app_config["layout_artifact_cleanup_max_repeated_text_chars"] == 80
    assert app_config["layout_artifact_cleanup_save_debug_artifacts"] is True
    assert app_config["reader_cleanup_default"] is False
    assert app_config["reader_cleanup_model"] == ""
    assert app_config["reader_cleanup_chunk_size"] == 8000
    assert app_config["reader_cleanup_overlap_blocks_before"] == 3
    assert app_config["reader_cleanup_overlap_blocks_after"] == 3
    assert app_config["reader_cleanup_global_plan_enabled"] is False


def test_load_app_config_exposes_image_validation_defaults(monkeypatch):
    monkeypatch.setattr(config, "CONFIG_PATH", config.CONFIG_PATH)

    app_config = config.load_app_config()
    models = cast(config.ModelRegistry, app_config["models"])

    assert app_config["enable_paragraph_markers"] is True
    assert app_config["processing_operation_default"] == "edit"
    assert app_config["source_language_default"] == "en"
    assert app_config["target_language_default"] == "ru"
    assert app_config["editorial_intensity_default"] == "literary"
    assert app_config["translation_domain_default"] == "general"
    supported_languages = cast(list[config.LanguageOption], app_config["supported_languages"])
    assert [language.code for language in supported_languages] == ["ru", "en", "de", "fr", "es", "it", "pl", "zh", "ja"]
    assert app_config["paragraph_boundary_normalization_enabled"] is True
    assert app_config["paragraph_boundary_normalization_mode"] == "high_only"
    assert app_config["paragraph_boundary_normalization_save_debug_artifacts"] is True
    # Prod default = "off": #2 structure-recovery cluster disabled on the prod path
    # (GLOBAL_PLAN 2026-06-22, PATH 2 / Task B). Restore to "auto" in config.toml to re-enable #2.
    assert models.text.default == TEST_TEXT_MODEL_DEFAULT
    assert models.text.options == (
        "gpt-5.4",
        "gpt-5.4-mini",
        "gpt-5-mini",
        "anthropic:claude-sonnet-4-6",
        "openrouter:anthropic/claude-sonnet-4.6",
        "openrouter:google/gemini-3.1-flash-lite-preview",
    )
    assert models.structure_recognition == TEST_TEXT_MODEL_DEFAULT
    assert app_config["structure_validation_block_on_high_risk_noop"] is True
    assert app_config["relation_normalization_enabled"] is True
    assert app_config["relation_normalization_profile"] == "phase2_default"
    assert app_config["relation_normalization_enabled_relation_kinds"] == (
        "image_caption",
        "table_caption",
        "epigraph_attribution",
        "toc_region",
    )
    assert app_config["relation_normalization_save_debug_artifacts"] is True
    assert app_config["layout_artifact_cleanup_enabled"] is True
    assert app_config["layout_artifact_cleanup_min_repeat_count"] == 3
    assert app_config["layout_artifact_cleanup_max_repeated_text_chars"] == 80
    assert app_config["layout_artifact_cleanup_save_debug_artifacts"] is True
    assert app_config["image_mode_default"] == "no_change"
    assert app_config["semantic_validation_policy"] == "advisory"
    assert app_config["keep_all_image_variants"] is False
    assert app_config["validation_model"] == TEST_IMAGE_VALIDATION_MODEL
    assert models.image_analysis == TEST_IMAGE_ANALYSIS_MODEL
    assert models.image_validation == TEST_IMAGE_VALIDATION_MODEL
    assert app_config["min_semantic_match_score"] == 0.75
    assert app_config["min_text_match_score"] == 0.8
    assert app_config["min_structure_match_score"] == 0.7
    assert app_config["validator_confidence_threshold"] == 0.75
    assert app_config["allow_accept_with_partial_text_loss"] is False
    assert app_config["prefer_deterministic_reconstruction"] is True
    assert app_config["reconstruction_model"] == TEST_IMAGE_RECONSTRUCTION_MODEL
    assert models.image_reconstruction == TEST_IMAGE_RECONSTRUCTION_MODEL
    assert models.image_generation == TEST_IMAGE_GENERATION_MODEL
    assert models.image_edit == TEST_IMAGE_EDIT_MODEL
    assert models.image_generation_vision == TEST_IMAGE_GENERATION_VISION_MODEL
    assert app_config["enable_vision_image_analysis"] is True
    assert app_config["enable_vision_image_validation"] is True
    assert app_config["semantic_redraw_max_attempts"] == 2
    assert app_config["semantic_redraw_max_model_calls_per_image"] == 9
    assert app_config["dense_text_bypass_threshold"] == 18
    assert app_config["non_latin_text_bypass_threshold"] == 12
    assert app_config["reconstruction_min_canvas_short_side_px"] == 900
    assert app_config["reconstruction_target_min_font_px"] == 18
    assert app_config["reconstruction_max_upscale_factor"] == 3.0
    assert app_config["image_output_generate_size_square"] == "1024x1024"
    assert app_config["image_output_generate_size_landscape"] == "1536x1024"
    assert app_config["image_output_generate_size_portrait"] == "1024x1536"
    assert app_config["image_output_generate_candidate_sizes"] == ("1536x1024", "1024x1536", "1024x1024")
    assert app_config["image_output_edit_candidate_sizes"] == ("1536x1024", "1024x1536", "1024x1024", "512x512", "256x256")
    assert app_config["image_output_aspect_ratio_threshold"] == 1.2
    assert app_config["image_output_trim_tolerance"] == 20
    assert app_config["image_output_trim_padding_ratio"] == 0.02
    assert app_config["image_output_trim_padding_min_px"] == 4
    assert app_config["image_output_trim_max_loss_ratio"] == 0.15
    assert app_config["reader_cleanup_default"] is False
    assert app_config["reader_cleanup_model"] == "anthropic:claude-sonnet-4-6"
    assert app_config["reader_cleanup_chunk_size"] == 8000
    assert app_config["reader_cleanup_overlap_blocks_before"] == 3
    assert app_config["reader_cleanup_overlap_blocks_after"] == 3
    assert app_config["reader_cleanup_global_plan_enabled"] is False


def test_load_app_config_applies_editorial_intensity_env_override(monkeypatch):
    monkeypatch.setattr(config, "CONFIG_PATH", config.CONFIG_PATH.parent / "__missing_config__.toml")
    monkeypatch.setenv("DOCX_AI_EDITORIAL_INTENSITY_DEFAULT", "conservative")

    app_config = config.load_app_config()

    assert app_config["editorial_intensity_default"] == "conservative"


def test_load_app_config_applies_translation_domain_env_override(monkeypatch):
    monkeypatch.setattr(config, "CONFIG_PATH", config.CONFIG_PATH.parent / "__missing_config__.toml")
    monkeypatch.setenv("DOCX_AI_TRANSLATION_DOMAIN_DEFAULT", "theology")

    app_config = config.load_app_config()

    assert app_config["translation_domain_default"] == "theology"


def test_load_app_config_applies_reader_cleanup_env_overrides(monkeypatch):
    monkeypatch.setattr(config, "CONFIG_PATH", config.CONFIG_PATH.parent / "__missing_config__.toml")
    monkeypatch.setenv("DOCX_AI_READER_CLEANUP_MODEL", "openrouter:anthropic/claude-haiku-4.5")
    monkeypatch.setenv("DOCX_AI_READER_CLEANUP_ENABLED", "true")

    app_config = config.load_app_config()

    assert app_config["reader_cleanup_model"] == "openrouter:anthropic/claude-haiku-4.5"
    assert app_config["reader_cleanup_default"] is True


def test_load_app_config_resolves_audiobook_defaults_from_text_model(monkeypatch):
    monkeypatch.setattr(config, "CONFIG_PATH", config.CONFIG_PATH.parent / "__missing_config__.toml")

    app_config = config.load_app_config()

    assert app_config["audiobook_postprocess_default"] is False
    assert app_config["audiobook_model"] == app_config["default_model"]


def test_load_app_config_honors_audiobook_model_override_from_toml(monkeypatch, tmp_path):
    cfg = tmp_path / "config.toml"
    cfg.write_text(
        '[models.text]\ndefault = "gpt-5.4-mini"\noptions = ["gpt-5.4-mini", "gpt-5.4"]\n\n'
        '[models.audiobook]\ndefault = "gpt-5.4"\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(config, "CONFIG_PATH", cfg)

    app_config = config.load_app_config()

    assert app_config["audiobook_model"] == "gpt-5.4"


def test_load_app_config_exposes_provider_registry_defaults(monkeypatch):
    monkeypatch.setattr(config, "CONFIG_PATH", config.CONFIG_PATH)

    app_config = config.load_app_config()
    providers = cast(config.ProviderRegistry, app_config["providers"])

    assert providers.openai.enabled is True
    assert providers.openai.api_key_env == "OPENAI_API_KEY"
    assert providers.openrouter.enabled is True
    assert providers.openrouter.api_key_env == "OPENROUTER_API_KEY"
    assert providers.openrouter.base_url == "https://openrouter.ai/api/v1"


def test_load_app_config_accepts_openrouter_text_selector(monkeypatch, tmp_path):
    cfg = tmp_path / "config.toml"
    cfg.write_text(
        '[models.text]\n'
        'default = "openrouter:google/gemini-3.1-flash-lite-preview"\n'
        'options = ["gpt-5.4-mini", "openrouter:google/gemini-3.1-flash-lite-preview"]\n\n'
        '[providers.openrouter]\n'
        'enabled = true\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(config, "CONFIG_PATH", cfg)

    app_config = config.load_app_config()

    assert app_config["default_model"] == "openrouter:google/gemini-3.1-flash-lite-preview"
    assert app_config["model_options"] == ["gpt-5.4-mini", "openrouter:google/gemini-3.1-flash-lite-preview"]


def test_load_app_config_rejects_duplicate_normalized_text_selectors(monkeypatch, tmp_path):
    cfg = tmp_path / "config.toml"
    cfg.write_text(
        '[models.text]\n'
        'default = "gpt-5.4-mini"\n'
        'options = ["gpt-5.4-mini", "openai:gpt-5.4-mini"]\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(config, "CONFIG_PATH", cfg)

    with pytest.raises(RuntimeError, match="duplicate normalized selectors"):
        config.load_app_config()


def test_load_app_config_rejects_openrouter_for_image_roles(monkeypatch, tmp_path):
    cfg = tmp_path / "config.toml"
    cfg.write_text(
        '[models.text]\n'
        'default = "gpt-5.4-mini"\n'
        'options = ["gpt-5.4-mini"]\n\n'
        '[models.image_generation]\n'
        'default = "openrouter:google/gemini-3.1-flash-lite-preview"\n\n'
        '[providers.openrouter]\n'
        'enabled = true\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(config, "CONFIG_PATH", cfg)

    with pytest.raises(RuntimeError, match=r"models\.image_generation\.default"):
        config.load_app_config()


def test_resolve_model_selector_normalizes_bare_openai_selector(monkeypatch):
    provider_registry = config.ProviderRegistry(
        openai=config.ProviderConfig(name="openai", enabled=True, api_key_env="OPENAI_API_KEY"),
        openrouter=config.ProviderConfig(name="openrouter", enabled=False, api_key_env="OPENROUTER_API_KEY"),
    )

    resolved = config.resolve_model_selector("gpt-5.4-mini", config_like=provider_registry)

    assert resolved.provider == "openai"
    assert resolved.model_id == "gpt-5.4-mini"
    assert resolved.canonical_selector == "openai:gpt-5.4-mini"


def test_describe_provider_availability_reports_missing_key(monkeypatch):
    app_config = config.AppConfig(
        models=config.ModelRegistry(
            text=config.TextModelConfig(default="gpt-5.4-mini", options=("gpt-5.4-mini",)),
            structure_recognition=TEST_STRUCTURE_RECOGNITION_MODEL,
            image_analysis=TEST_IMAGE_ANALYSIS_MODEL,
            image_validation=TEST_IMAGE_VALIDATION_MODEL,
            image_reconstruction=TEST_IMAGE_RECONSTRUCTION_MODEL,
            image_generation=TEST_IMAGE_GENERATION_MODEL,
            image_edit=TEST_IMAGE_EDIT_MODEL,
            image_generation_vision=TEST_IMAGE_GENERATION_VISION_MODEL,
        ),
        providers=config.ProviderRegistry(
            openai=config.ProviderConfig(name="openai", enabled=True, api_key_env="OPENAI_API_KEY"),
            openrouter=config.ProviderConfig(name="openrouter", enabled=True, api_key_env="OPENROUTER_API_KEY", base_url="https://openrouter.ai/api/v1", referer="DocxAICorrector", title="DocxAICorrector"),
        ),
        default_model="gpt-5.4-mini",
        model_options=["gpt-5.4-mini"],
        chunk_size=6000,
        max_retries=3,
        processing_operation_default="edit",
        source_language_default="en",
        target_language_default="ru",
        editorial_intensity_default="literary",
        translation_domain_default="general",
        audiobook_postprocess_default=False,
        audiobook_model="gpt-5.4-mini",
        supported_languages=tuple(),
        enable_paragraph_markers=False,
        paragraph_boundary_normalization_enabled=True,
        paragraph_boundary_normalization_mode="high_only",
        paragraph_boundary_normalization_save_debug_artifacts=True,
        paragraph_boundary_ai_review_enabled=False,
        paragraph_boundary_ai_review_mode="off",
        paragraph_boundary_ai_review_candidate_limit=200,
        paragraph_boundary_ai_review_timeout_seconds=30,
        paragraph_boundary_ai_review_max_tokens_per_candidate=120,
        layout_artifact_cleanup_enabled=True,
        layout_artifact_cleanup_min_repeat_count=3,
        layout_artifact_cleanup_max_repeated_text_chars=80,
        layout_artifact_cleanup_save_debug_artifacts=True,
        relation_normalization_enabled=True,
        relation_normalization_profile="phase2_default",
        relation_normalization_enabled_relation_kinds=("image_caption",),
        relation_normalization_save_debug_artifacts=True,
        structure_validation_enabled=True,
        structure_validation_min_paragraphs_for_auto_gate=40,
        structure_validation_min_explicit_heading_density=0.003,
        structure_validation_max_suspicious_short_body_ratio_without_escalation=0.05,
        structure_validation_max_all_caps_or_centered_body_ratio_without_escalation=0.03,
        structure_validation_toc_like_sequence_min_length=4,
        structure_validation_forbid_heading_only_collapse=True,
        structure_validation_save_debug_artifacts=True,
        structure_validation_block_on_high_risk_noop=True,
        output_body_font=None,
        output_heading_font=None,
        image_mode_default="no_change",
        semantic_validation_policy="advisory",
        keep_all_image_variants=False,
        validation_model=TEST_IMAGE_VALIDATION_MODEL,
        min_semantic_match_score=0.75,
        min_text_match_score=0.8,
        min_structure_match_score=0.7,
        validator_confidence_threshold=0.75,
        allow_accept_with_partial_text_loss=False,
        prefer_deterministic_reconstruction=True,
        reconstruction_model=TEST_IMAGE_RECONSTRUCTION_MODEL,
        enable_vision_image_analysis=True,
        enable_vision_image_validation=True,
        semantic_redraw_max_attempts=2,
        semantic_redraw_max_model_calls_per_image=9,
        dense_text_bypass_threshold=18,
        non_latin_text_bypass_threshold=12,
        reconstruction_min_canvas_short_side_px=900,
        reconstruction_target_min_font_px=18,
        reconstruction_max_upscale_factor=3.0,
        reconstruction_background_sample_ratio=0.04,
        reconstruction_background_color_distance_threshold=48.0,
        reconstruction_background_uniformity_threshold=10.0,
        image_output_generate_size_square="1024x1024",
        image_output_generate_size_landscape="1536x1024",
        image_output_generate_size_portrait="1024x1536",
        image_output_generate_candidate_sizes=("1536x1024",),
        image_output_edit_candidate_sizes=("1536x1024",),
        image_output_aspect_ratio_threshold=1.2,
        image_output_trim_tolerance=20,
        image_output_trim_padding_ratio=0.02,
        image_output_trim_padding_min_px=4,
        image_output_trim_max_loss_ratio=0.15,
    )
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    availability = config.describe_provider_availability(
        "openrouter:google/gemini-3.1-flash-lite-preview",
        app_config=app_config,
    )

    assert availability.has_api_key is False
    assert availability.error_message == (
        "Для модели 'openrouter:google/gemini-3.1-flash-lite-preview' не найден OPENROUTER_API_KEY."
    )


def test_describe_provider_availability_loads_project_dotenv(monkeypatch):
    app_config = config.AppConfig(
        models=config.ModelRegistry(
            text=config.TextModelConfig(default="gpt-5.4-mini", options=("gpt-5.4-mini",)),
            structure_recognition=TEST_STRUCTURE_RECOGNITION_MODEL,
            image_analysis=TEST_IMAGE_ANALYSIS_MODEL,
            image_validation=TEST_IMAGE_VALIDATION_MODEL,
            image_reconstruction=TEST_IMAGE_RECONSTRUCTION_MODEL,
            image_generation=TEST_IMAGE_GENERATION_MODEL,
            image_edit=TEST_IMAGE_EDIT_MODEL,
            image_generation_vision=TEST_IMAGE_GENERATION_VISION_MODEL,
        ),
        providers=config.ProviderRegistry(
            openai=config.ProviderConfig(name="openai", enabled=True, api_key_env="OPENAI_API_KEY"),
            openrouter=config.ProviderConfig(name="openrouter", enabled=True, api_key_env="OPENROUTER_API_KEY", base_url="https://openrouter.ai/api/v1", referer="DocxAICorrector", title="DocxAICorrector"),
        ),
        default_model="gpt-5.4-mini",
        model_options=["gpt-5.4-mini"],
        chunk_size=6000,
        max_retries=3,
        processing_operation_default="edit",
        source_language_default="en",
        target_language_default="ru",
        editorial_intensity_default="literary",
        translation_domain_default="general",
        audiobook_postprocess_default=False,
        audiobook_model="gpt-5.4-mini",
        supported_languages=tuple(),
        enable_paragraph_markers=False,
        paragraph_boundary_normalization_enabled=True,
        paragraph_boundary_normalization_mode="high_only",
        paragraph_boundary_normalization_save_debug_artifacts=True,
        paragraph_boundary_ai_review_enabled=False,
        paragraph_boundary_ai_review_mode="off",
        paragraph_boundary_ai_review_candidate_limit=200,
        paragraph_boundary_ai_review_timeout_seconds=30,
        paragraph_boundary_ai_review_max_tokens_per_candidate=120,
        layout_artifact_cleanup_enabled=True,
        layout_artifact_cleanup_min_repeat_count=3,
        layout_artifact_cleanup_max_repeated_text_chars=80,
        layout_artifact_cleanup_save_debug_artifacts=True,
        relation_normalization_enabled=True,
        relation_normalization_profile="phase2_default",
        relation_normalization_enabled_relation_kinds=("image_caption",),
        relation_normalization_save_debug_artifacts=True,
        structure_validation_enabled=True,
        structure_validation_min_paragraphs_for_auto_gate=40,
        structure_validation_min_explicit_heading_density=0.003,
        structure_validation_max_suspicious_short_body_ratio_without_escalation=0.05,
        structure_validation_max_all_caps_or_centered_body_ratio_without_escalation=0.03,
        structure_validation_toc_like_sequence_min_length=4,
        structure_validation_forbid_heading_only_collapse=True,
        structure_validation_save_debug_artifacts=True,
        structure_validation_block_on_high_risk_noop=True,
        output_body_font=None,
        output_heading_font=None,
        image_mode_default="no_change",
        semantic_validation_policy="advisory",
        keep_all_image_variants=False,
        validation_model=TEST_IMAGE_VALIDATION_MODEL,
        min_semantic_match_score=0.75,
        min_text_match_score=0.8,
        min_structure_match_score=0.7,
        validator_confidence_threshold=0.75,
        allow_accept_with_partial_text_loss=False,
        prefer_deterministic_reconstruction=True,
        reconstruction_model=TEST_IMAGE_RECONSTRUCTION_MODEL,
        enable_vision_image_analysis=True,
        enable_vision_image_validation=True,
        semantic_redraw_max_attempts=2,
        semantic_redraw_max_model_calls_per_image=9,
        dense_text_bypass_threshold=18,
        non_latin_text_bypass_threshold=12,
        reconstruction_min_canvas_short_side_px=900,
        reconstruction_target_min_font_px=18,
        reconstruction_max_upscale_factor=3.0,
        reconstruction_background_sample_ratio=0.04,
        reconstruction_background_color_distance_threshold=48.0,
        reconstruction_background_uniformity_threshold=10.0,
        image_output_generate_size_square="1024x1024",
        image_output_generate_size_landscape="1536x1024",
        image_output_generate_size_portrait="1024x1536",
        image_output_generate_candidate_sizes=("1536x1024",),
        image_output_edit_candidate_sizes=("1536x1024",),
        image_output_aspect_ratio_threshold=1.2,
        image_output_trim_tolerance=20,
        image_output_trim_padding_ratio=0.02,
        image_output_trim_padding_min_px=4,
        image_output_trim_max_loss_ratio=0.15,
    )
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    def _fake_load_project_dotenv() -> None:
        os.environ["OPENROUTER_API_KEY"] = "test-openrouter-key"

    monkeypatch.setattr(config, "load_project_dotenv", _fake_load_project_dotenv)

    availability = config.describe_provider_availability(
        "openrouter:google/gemini-3.1-flash-lite-preview",
        app_config=app_config,
    )

    assert availability.has_api_key is True
    assert availability.error_message is None


def test_load_app_config_applies_audiobook_postprocess_env_override(monkeypatch):
    monkeypatch.setattr(config, "CONFIG_PATH", config.CONFIG_PATH.parent / "__missing_config__.toml")
    monkeypatch.setenv("DOCX_AI_AUDIOBOOK_POSTPROCESS_DEFAULT", "true")

    app_config = config.load_app_config()

    assert app_config["audiobook_postprocess_default"] is True


def test_load_system_prompt_varies_by_editorial_intensity():
    literary_prompt = config.load_system_prompt(
        operation="translate",
        source_language="en",
        target_language="ru",
        editorial_intensity="literary",
    )
    conservative_prompt = config.load_system_prompt(
        operation="translate",
        source_language="en",
        target_language="ru",
        editorial_intensity="conservative",
    )

    assert literary_prompt != conservative_prompt
    assert "словно заново выдумывал себя у всех на глазах" in literary_prompt
    assert "Работайте с текстом сдержанно и аккуратно." in conservative_prompt
    assert "Preserve every marker [[DOCX_PARA_...]] exactly as it appears" not in literary_prompt


def test_load_system_prompt_includes_theology_domain_instructions():
    theology_prompt = config.load_system_prompt(
        operation="translate",
        source_language="en",
        target_language="ru",
        editorial_intensity="literary",
        translation_domain="theology",
        source_text="The Great Tribulation and the rapture precede the rise of the Antichrist.",
    )

    assert "ДОМЕН ПЕРЕВОДА: богословие / эсхатология." in theology_prompt
    assert "Great Tribulation -> Великая скорбь" in theology_prompt
    assert "rapture -> восхищение Церкви / восхищение верующих" in theology_prompt


def test_load_system_prompt_rejects_unsupported_editorial_intensity():
    with pytest.raises(RuntimeError, match="Некорректная editorial_intensity"):
        config.load_system_prompt(
            operation="translate",
            source_language="en",
            target_language="ru",
            editorial_intensity="aggressive",
        )


def test_load_app_config_applies_image_env_overrides_and_clamps(monkeypatch):
    monkeypatch.setattr(config, "CONFIG_PATH", config.CONFIG_PATH.parent / "__missing_config__.toml")
    monkeypatch.setenv("DOCX_AI_IMAGE_MODE_DEFAULT", "semantic_redraw_direct")
    monkeypatch.setenv("DOCX_AI_SEMANTIC_VALIDATION_POLICY", "strict")
    monkeypatch.setenv("DOCX_AI_KEEP_ALL_IMAGE_VARIANTS", "true")
    monkeypatch.setenv("DOCX_AI_VALIDATION_MODEL", "gpt-5.4")
    monkeypatch.setenv("DOCX_AI_MIN_SEMANTIC_MATCH_SCORE", "1.2")
    monkeypatch.setenv("DOCX_AI_MIN_TEXT_MATCH_SCORE", "-0.1")
    monkeypatch.setenv("DOCX_AI_MIN_STRUCTURE_MATCH_SCORE", "0.91")
    monkeypatch.setenv("DOCX_AI_VALIDATOR_CONFIDENCE_THRESHOLD", "2")
    monkeypatch.setenv("DOCX_AI_ALLOW_ACCEPT_WITH_PARTIAL_TEXT_LOSS", "yes")
    monkeypatch.setenv("DOCX_AI_PREFER_DETERMINISTIC_RECONSTRUCTION", "false")
    monkeypatch.setenv("DOCX_AI_ENABLE_PARAGRAPH_MARKERS", "true")
    monkeypatch.setenv("DOCX_AI_RECONSTRUCTION_MODEL", "gpt-5-mini")
    monkeypatch.setenv("DOCX_AI_ENABLE_VISION_IMAGE_ANALYSIS", "false")
    monkeypatch.setenv("DOCX_AI_ENABLE_VISION_IMAGE_VALIDATION", "false")
    monkeypatch.setenv("DOCX_AI_SEMANTIC_REDRAW_MAX_ATTEMPTS", "9")
    monkeypatch.setenv("DOCX_AI_SEMANTIC_REDRAW_MAX_MODEL_CALLS_PER_IMAGE", "99")
    monkeypatch.setenv("DOCX_AI_DENSE_TEXT_BYPASS_THRESHOLD", "99")
    monkeypatch.setenv("DOCX_AI_NON_LATIN_TEXT_BYPASS_THRESHOLD", "77")
    monkeypatch.setenv("DOCX_AI_RECONSTRUCTION_MIN_CANVAS_SHORT_SIDE_PX", "8192")
    monkeypatch.setenv("DOCX_AI_RECONSTRUCTION_TARGET_MIN_FONT_PX", "8")
    monkeypatch.setenv("DOCX_AI_RECONSTRUCTION_MAX_UPSCALE_FACTOR", "9")
    monkeypatch.setenv("DOCX_AI_IMAGE_OUTPUT_GENERATE_SIZE_SQUARE", "1536x1024")
    monkeypatch.setenv("DOCX_AI_IMAGE_OUTPUT_GENERATE_SIZE_LANDSCAPE", "1024x1024")
    monkeypatch.setenv("DOCX_AI_IMAGE_OUTPUT_GENERATE_SIZE_PORTRAIT", "1024x1024")
    monkeypatch.setenv("DOCX_AI_IMAGE_OUTPUT_GENERATE_CANDIDATE_SIZES", "1024x1024,1536x1024")
    monkeypatch.setenv("DOCX_AI_IMAGE_OUTPUT_EDIT_CANDIDATE_SIZES", "512x512,256x256")
    monkeypatch.setenv("DOCX_AI_IMAGE_OUTPUT_ASPECT_RATIO_THRESHOLD", "9")
    monkeypatch.setenv("DOCX_AI_IMAGE_OUTPUT_TRIM_TOLERANCE", "99")
    monkeypatch.setenv("DOCX_AI_IMAGE_OUTPUT_TRIM_PADDING_RATIO", "9")
    monkeypatch.setenv("DOCX_AI_IMAGE_OUTPUT_TRIM_PADDING_MIN_PX", "999")
    monkeypatch.setenv("DOCX_AI_IMAGE_OUTPUT_TRIM_MAX_LOSS_RATIO", "9")

    app_config = config.load_app_config()
    models = cast(config.ModelRegistry, app_config["models"])

    assert app_config["image_mode_default"] == "semantic_redraw_direct"
    assert app_config["semantic_validation_policy"] == "strict"
    assert app_config["keep_all_image_variants"] is True
    assert app_config["validation_model"] == "gpt-5.4"
    assert models.image_analysis == "gpt-5.4"
    assert models.image_validation == "gpt-5.4"
    assert app_config["min_semantic_match_score"] == 1.0
    assert app_config["min_text_match_score"] == 0.0
    assert app_config["min_structure_match_score"] == 0.91
    assert app_config["validator_confidence_threshold"] == 1.0
    assert app_config["allow_accept_with_partial_text_loss"] is True
    assert app_config["prefer_deterministic_reconstruction"] is False
    assert app_config["enable_paragraph_markers"] is True
    assert app_config["reconstruction_model"] == "gpt-5-mini"
    assert models.image_reconstruction == "gpt-5-mini"
    assert app_config["enable_vision_image_analysis"] is False
    assert app_config["enable_vision_image_validation"] is False
    assert app_config["semantic_redraw_max_attempts"] == 2
    assert app_config["semantic_redraw_max_model_calls_per_image"] == 20
    assert app_config["dense_text_bypass_threshold"] == 80
    assert app_config["non_latin_text_bypass_threshold"] == 77
    assert app_config["reconstruction_min_canvas_short_side_px"] == 4096
    assert app_config["reconstruction_target_min_font_px"] == 10
    assert app_config["reconstruction_max_upscale_factor"] == 6.0
    assert app_config["image_output_generate_size_square"] == "1536x1024"
    assert app_config["image_output_generate_size_landscape"] == "1024x1024"
    assert app_config["image_output_generate_size_portrait"] == "1024x1024"
    assert app_config["image_output_generate_candidate_sizes"] == ("1024x1024", "1536x1024")
    assert app_config["image_output_edit_candidate_sizes"] == ("512x512", "256x256")
    assert app_config["image_output_aspect_ratio_threshold"] == 3.0
    assert app_config["image_output_trim_tolerance"] == 64
    assert app_config["image_output_trim_padding_ratio"] == 0.25
    assert app_config["image_output_trim_padding_min_px"] == 128
    assert app_config["image_output_trim_max_loss_ratio"] == 0.49


def test_load_app_config_rejects_invalid_image_output_size_override(monkeypatch):
    monkeypatch.setattr(config, "CONFIG_PATH", config.CONFIG_PATH.parent / "__missing_config__.toml")
    monkeypatch.setenv("DOCX_AI_IMAGE_OUTPUT_GENERATE_SIZE_SQUARE", "2048x2048")

    with pytest.raises(RuntimeError, match="DOCX_AI_IMAGE_OUTPUT_GENERATE_SIZE_SQUARE"):
        config.load_app_config()


def test_load_app_config_rejects_invalid_image_output_size_list_override(monkeypatch):
    monkeypatch.setattr(config, "CONFIG_PATH", config.CONFIG_PATH.parent / "__missing_config__.toml")
    monkeypatch.setenv("DOCX_AI_IMAGE_OUTPUT_GENERATE_CANDIDATE_SIZES", "2048x2048")

    with pytest.raises(RuntimeError, match="DOCX_AI_IMAGE_OUTPUT_GENERATE_CANDIDATE_SIZES"):
        config.load_app_config()


def test_load_app_config_rejects_invalid_paragraph_boundary_mode(monkeypatch, tmp_path):
    cfg = tmp_path / "config.toml"
    cfg.write_text(
        '[paragraph_boundary_normalization]\nmode = "aggressive"\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(config, "CONFIG_PATH", cfg)

    with pytest.raises(RuntimeError, match="mode"):
        config.load_app_config()


def test_load_app_config_accepts_high_and_medium_paragraph_boundary_mode(monkeypatch, tmp_path):
    cfg = tmp_path / "config.toml"
    cfg.write_text(
        '[paragraph_boundary_normalization]\nmode = "high_and_medium"\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(config, "CONFIG_PATH", cfg)

    app_config = config.load_app_config()

    assert app_config["paragraph_boundary_normalization_mode"] == "high_and_medium"


def test_load_app_config_rejects_auto_source_language_default_for_edit_mode(monkeypatch, tmp_path):
    cfg = tmp_path / "config.toml"
    cfg.write_text(
        'processing_operation_default = "edit"\nsource_language_default = "auto"\ntarget_language_default = "ru"\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(config, "CONFIG_PATH", cfg)

    with pytest.raises(RuntimeError, match="source_language='auto'"):
        config.load_app_config()


def test_load_system_prompt_rejects_auto_source_language_for_edit_mode():
    config.load_system_prompt.cache_clear()
    try:
        with pytest.raises(RuntimeError, match="source_language='auto'"):
            config.load_system_prompt(operation="edit", source_language="auto", target_language="ru")
    finally:
        config.load_system_prompt.cache_clear()


def test_load_system_prompt_edit_includes_local_fragment_repair_guardrails():
    config.load_system_prompt.cache_clear()
    try:
        prompt = config.load_system_prompt(operation="edit", source_language="ru", target_language="ru")
    finally:
        config.load_system_prompt.cache_clear()

    assert "явно разорванное предложение" in prompt
    assert "минимально восстановить локальную связность" in prompt
    assert "не переносите текст через очевидные структурные границы" in prompt
    assert "не меняйте тип элемента" in prompt
    assert "Не меняйте структуру абзацев сверх того" in prompt


def test_load_system_prompt_translate_includes_local_fragment_repair_guardrails():
    config.load_system_prompt.cache_clear()
    try:
        prompt = config.load_system_prompt(operation="translate", source_language="en", target_language="ru")
    finally:
        config.load_system_prompt.cache_clear()

    assert "явно разорванное предложение" in prompt
    assert "не нарушает прямые ограничения выбранного режима обработки" in prompt
    assert "не превращайте локальный repair в общую перестройку структуры" in prompt


def test_load_system_prompt_audiobook_includes_local_fragment_repair_guardrails():
    config.load_system_prompt.cache_clear()
    try:
        prompt = config.load_system_prompt(operation="audiobook", source_language="en", target_language="ru")
    finally:
        config.load_system_prompt.cache_clear()

    assert "явно разорванное предложение" in prompt
    assert "не нарушает прямые ограничения выбранного режима обработки" in prompt
    assert "не превращайте локальный repair в общую перестройку структуры" in prompt


def test_load_system_prompt_translate_includes_hardening_rules():
    config.load_system_prompt.cache_clear()
    try:
        prompt = config.load_system_prompt(operation="translate", source_language="en", target_language="ru")
    finally:
        config.load_system_prompt.cache_clear()

    assert "не выполняйте повторный перевод" in prompt
    assert "ориентируйтесь в первую очередь на фактический язык блока" in prompt
    assert "предпочитайте консервативный результат" in prompt


def test_load_system_prompt_supports_audiobook_operation():
    config.load_system_prompt.cache_clear()
    try:
        prompt = config.load_system_prompt(operation="audiobook", source_language="en", target_language="ru")
    finally:
        config.load_system_prompt.cache_clear()

    assert "ElevenLabs Audiobooks" in prompt
    assert "[thoughtful]" in prompt
    assert "готовый для TTS" in prompt


def test_load_system_prompt_audiobook_includes_narration_adapted_rules():
    config.load_system_prompt.cache_clear()
    try:
        prompt = config.load_system_prompt(operation="audiobook", source_language="en", target_language="ru")
    finally:
        config.load_system_prompt.cache_clear()

    assert "narration_adapted" in prompt
    assert "разбивайте его на два или три более коротких spoken sentences" in prompt
    assert "light paraphrase for spoken clarity" in prompt
    assert "Не делайте summarization" in prompt
    assert "load-bearing clauses" in prompt
    assert "causal links" in prompt
    assert "Adaptation is selective, not mandatory" in prompt


def test_load_system_prompt_audiobook_preserves_meaning_guardrails():
    config.load_system_prompt.cache_clear()
    try:
        prompt = config.load_system_prompt(operation="audiobook", source_language="en", target_language="ru")
    finally:
        config.load_system_prompt.cache_clear()

    assert "named entities, даты, числа, quantitative claims" in prompt
    assert "Не смягчайте и не усиливайте тезис автора" in prompt
    assert "Не добавляйте новую интерпретацию от себя" in prompt
    assert "Если термин semantically important, сохраняйте его" in prompt


def test_load_system_prompt_audiobook_examples_include_sentence_splitting_and_negative_contrast():
    config.load_system_prompt.cache_clear()
    try:
        prompt = config.load_system_prompt(operation="audiobook", source_language="en", target_language="ru")
    finally:
        config.load_system_prompt.cache_clear()

    assert "Финансовые операции и порождаемая ими ментальность" in prompt
    assert "Это видно по решениям менеджеров." in prompt
    assert "Некорректно" in prompt
    assert "потеряны qualifier `может`" in prompt


def test_load_system_prompt_supports_auto_source_language_for_audiobook():
    config.load_system_prompt.cache_clear()
    try:
        prompt = config.load_system_prompt(operation="audiobook", source_language="auto", target_language="ru")
    finally:
        config.load_system_prompt.cache_clear()

    assert "определи автоматически по тексту" in prompt


def test_load_system_prompt_translate_includes_editorial_intensity_fragment_and_example_rules():
    config.load_system_prompt.cache_clear()
    try:
        prompt = config.load_system_prompt(
            operation="translate",
            source_language="en",
            target_language="ru",
            editorial_intensity="literary",
        )
    finally:
        config.load_system_prompt.cache_clear()

    assert "словно заново выдумывал себя у всех на глазах" in prompt
    assert "Стремитесь к литературно естественному тексту на языке Русский" in prompt
    assert "[[DOCX_IMAGE_img_001]]" in prompt
    assert "[[DOCX_PARA_...]]" in prompt


def test_load_system_prompt_cache_distinguishes_editorial_intensity_modes():
    config.load_system_prompt.cache_clear()
    try:
        initial = config.load_system_prompt.cache_info()

        literary_prompt = config.load_system_prompt(
            operation="translate",
            source_language="en",
            target_language="ru",
            editorial_intensity="literary",
        )
        after_first = config.load_system_prompt.cache_info()

        repeated_literary_prompt = config.load_system_prompt(
            operation="translate",
            source_language="en",
            target_language="ru",
            editorial_intensity="literary",
        )
        after_second = config.load_system_prompt.cache_info()

        conservative_prompt = config.load_system_prompt(
            operation="translate",
            source_language="en",
            target_language="ru",
            editorial_intensity="conservative",
        )
        after_third = config.load_system_prompt.cache_info()
    finally:
        config.load_system_prompt.cache_clear()

    assert literary_prompt == repeated_literary_prompt
    assert literary_prompt != conservative_prompt
    assert after_first.misses == initial.misses + 1
    assert after_second.hits == after_first.hits + 1
    assert after_third.misses == after_second.misses + 1


def test_load_system_prompt_supports_literary_polish_variant():
    config.load_system_prompt.cache_clear()
    try:
        prompt = config.load_system_prompt(
            operation="translate",
            source_language="en",
            target_language="ru",
            editorial_intensity="literary",
            prompt_variant="literary_polish",
        )
    finally:
        config.load_system_prompt.cache_clear()

    assert "Текст уже находится на языке Русский. Не переводите его заново." in prompt
    assert "Выполните только литературную полировку" in prompt
    assert "словно заново выдумывал себя у всех на глазах" in prompt


def test_load_system_prompt_supports_toc_translate_variant():
    config.load_system_prompt.cache_clear()
    try:
        prompt = config.load_system_prompt(
            operation="translate",
            source_language="en",
            target_language="ru",
            editorial_intensity="literary",
            prompt_variant="toc_translate",
        )
    finally:
        config.load_system_prompt.cache_clear()

    assert "Переведите блок как оглавление" in prompt
    assert "Содержание" in prompt
    assert "Part II: The Dynamics of Extraction ........ 83" in prompt


def test_load_app_config_accepts_audiobook_processing_operation_default(monkeypatch, tmp_path):
    cfg = tmp_path / "config.toml"
    cfg.write_text(
        'processing_operation_default = "audiobook"\nsource_language_default = "auto"\ntarget_language_default = "ru"\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(config, "CONFIG_PATH", cfg)

    app_config = config.load_app_config()

    assert app_config["processing_operation_default"] == "audiobook"


def test_load_app_config_applies_env_override_for_paragraph_boundary_mode(monkeypatch, tmp_path):
    cfg = tmp_path / "config.toml"
    cfg.write_text(
        '[paragraph_boundary_normalization]\nmode = "high_only"\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(config, "CONFIG_PATH", cfg)
    monkeypatch.setenv("DOCX_AI_PARAGRAPH_BOUNDARY_NORMALIZATION_MODE", "high_and_medium")

    app_config = config.load_app_config()

    assert app_config["paragraph_boundary_normalization_mode"] == "high_and_medium"


def test_load_app_config_exposes_paragraph_boundary_ai_review_defaults(monkeypatch):
    monkeypatch.setattr(config, "CONFIG_PATH", config.CONFIG_PATH)

    app_config = config.load_app_config()

    assert app_config["paragraph_boundary_ai_review_enabled"] is False
    assert app_config["paragraph_boundary_ai_review_mode"] == "off"
    assert app_config["paragraph_boundary_ai_review_candidate_limit"] == 200
    assert app_config["paragraph_boundary_ai_review_timeout_seconds"] == 30
    assert app_config["paragraph_boundary_ai_review_max_tokens_per_candidate"] == 120


def test_load_app_config_applies_paragraph_boundary_ai_review_env_overrides(monkeypatch):
    monkeypatch.setattr(config, "CONFIG_PATH", config.CONFIG_PATH.parent / "__missing_config__.toml")
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")
    monkeypatch.setenv("DOCX_AI_PARAGRAPH_BOUNDARY_AI_REVIEW_ENABLED", "true")
    monkeypatch.setenv("DOCX_AI_PARAGRAPH_BOUNDARY_AI_REVIEW_MODE", "review_only")
    monkeypatch.setenv("DOCX_AI_PARAGRAPH_BOUNDARY_AI_REVIEW_CANDIDATE_LIMIT", "999")
    monkeypatch.setenv("DOCX_AI_PARAGRAPH_BOUNDARY_AI_REVIEW_TIMEOUT_SECONDS", "0")
    monkeypatch.setenv("DOCX_AI_PARAGRAPH_BOUNDARY_AI_REVIEW_MAX_TOKENS_PER_CANDIDATE", "9999")

    app_config = config.load_app_config()

    assert app_config["paragraph_boundary_ai_review_enabled"] is True
    assert app_config["paragraph_boundary_ai_review_mode"] == "review_only"
    assert app_config["paragraph_boundary_ai_review_candidate_limit"] == 500
    assert app_config["paragraph_boundary_ai_review_timeout_seconds"] == 1
    assert app_config["paragraph_boundary_ai_review_max_tokens_per_candidate"] == 512


def test_load_app_config_applies_layout_cleanup_env_overrides(monkeypatch):
    monkeypatch.setattr(config, "CONFIG_PATH", config.CONFIG_PATH.parent / "__missing_config__.toml")
    monkeypatch.setenv("DOCX_AI_LAYOUT_ARTIFACT_CLEANUP_ENABLED", "false")
    monkeypatch.setenv("DOCX_AI_LAYOUT_ARTIFACT_CLEANUP_MIN_REPEAT_COUNT", "999")
    monkeypatch.setenv("DOCX_AI_LAYOUT_ARTIFACT_CLEANUP_MAX_REPEATED_TEXT_CHARS", "0")
    monkeypatch.setenv("DOCX_AI_LAYOUT_ARTIFACT_CLEANUP_SAVE_DEBUG_ARTIFACTS", "false")

    app_config = config.load_app_config()

    assert app_config["layout_artifact_cleanup_enabled"] is False
    assert app_config["layout_artifact_cleanup_min_repeat_count"] == 100
    assert app_config["layout_artifact_cleanup_max_repeated_text_chars"] == 1
    assert app_config["layout_artifact_cleanup_save_debug_artifacts"] is False


def test_load_app_config_rejects_invalid_env_override_for_paragraph_boundary_mode(monkeypatch):
    monkeypatch.setattr(config, "CONFIG_PATH", config.CONFIG_PATH.parent / "__missing_config__.toml")
    monkeypatch.setenv("DOCX_AI_PARAGRAPH_BOUNDARY_NORMALIZATION_MODE", "aggressive")

    with pytest.raises(RuntimeError, match="DOCX_AI_PARAGRAPH_BOUNDARY_NORMALIZATION_MODE"):
        config.load_app_config()


def test_load_app_config_emits_legacy_model_warnings_only_once(monkeypatch, tmp_path):
    cfg = tmp_path / "config.toml"
    cfg.write_text(
        'default_model = "legacy-text"\n'
        'model_options = ["legacy-text", "legacy-alt"]\n'
        'validation_model = "legacy-validation"\n'
        '[structure_recognition]\nmodel = "legacy-structure"\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(config, "CONFIG_PATH", cfg)
    monkeypatch.setattr(config, "_EMITTED_MODEL_REGISTRY_LOG_KEYS", set())
    log_calls = []
    monkeypatch.setattr(config, "log_event", lambda level, event, message, **context: log_calls.append((event, context)))

    config.load_app_config()
    first_call_count = len(log_calls)
    config.load_app_config()

    assert first_call_count > 0
    assert len(log_calls) == first_call_count


def test_parse_csv_env_rejects_empty_effective_list(monkeypatch):
    monkeypatch.setenv("DOCX_AI_MODEL_OPTIONS", " , , ")

    try:
        config.parse_csv_env("DOCX_AI_MODEL_OPTIONS")
    except RuntimeError as exc:
        assert "список моделей пуст" in str(exc)
    else:
        raise AssertionError("Expected RuntimeError for an empty CSV env override")


def test_load_app_config_rejects_duplicate_canonical_text_model_options(monkeypatch, tmp_path):
    cfg = tmp_path / "config.toml"
    cfg.write_text(
        '[models.text]\ndefault = "gpt-5.4-mini"\noptions = ["gpt-5.4-mini", "gpt-5.4-mini", "gpt-5.4"]\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(config, "CONFIG_PATH", cfg)

    with pytest.raises(RuntimeError, match=r"models\.text\.options"):
        config.load_app_config()


def test_get_model_role_value_rejects_runtime_legacy_role_aliases() -> None:
    with pytest.raises(RuntimeError, match="image_validation"):
        config.get_model_role_value({"validation_model": "legacy-validation"}, "image_validation")


def test_get_text_model_helpers_require_runtime_model_registry_shape() -> None:
    with pytest.raises(RuntimeError, match="Text default model"):
        config.get_text_model_default(
            {
                "default_model": "legacy-text",
                "model_options": ["legacy-text", "legacy-alt"],
            }
        )


def test_get_model_registry_rejects_legacy_only_runtime_shape() -> None:
    with pytest.raises(RuntimeError, match="Text default model"):
        config.get_model_registry(
            {
                "default_model": "legacy-text",
                "model_options": ["legacy-text", "legacy-alt"],
                "validation_model": "legacy-validation",
                "reconstruction_model": "legacy-reconstruction",
            }
        )


def test_load_app_config_prefers_canonical_model_registry_over_legacy_env(monkeypatch, tmp_path):
    cfg = tmp_path / "config.toml"
    cfg.write_text(
        '[models.text]\ndefault = "gpt-5.4-mini"\noptions = ["gpt-5.4-mini", "gpt-5.4"]\n\n'
        '[models.image_validation]\ndefault = "gpt-5.4-mini"\n\n'
        '[models.image_analysis]\ndefault = "gpt-5-mini"\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(config, "CONFIG_PATH", cfg)
    monkeypatch.setenv("DOCX_AI_DEFAULT_MODEL", "legacy-model")
    monkeypatch.setenv("DOCX_AI_VALIDATION_MODEL", "legacy-validation")

    app_config = config.load_app_config()
    models = cast(config.ModelRegistry, app_config["models"])

    assert models.text.default == "gpt-5.4-mini"
    assert app_config["default_model"] == "gpt-5.4-mini"
    assert models.image_validation == "gpt-5.4-mini"
    assert app_config["validation_model"] == "gpt-5.4-mini"
    assert models.image_analysis == "gpt-5-mini"


def test_load_app_config_new_env_overrides_legacy_toml_models(monkeypatch, tmp_path):
    cfg = tmp_path / "config.toml"
    cfg.write_text(
        'default_model = "legacy-text"\n'
        'model_options = ["legacy-text", "legacy-alt"]\n'
        'validation_model = "legacy-validation"\n'
        'reconstruction_model = "legacy-reconstruction"\n'
        '[structure_recognition]\nmodel = "legacy-structure"\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(config, "CONFIG_PATH", cfg)
    monkeypatch.setenv("DOCX_AI_MODELS_TEXT_DEFAULT", "gpt-5.4")
    monkeypatch.setenv("DOCX_AI_MODELS_TEXT_OPTIONS", "gpt-5.4,gpt-5.4-mini")
    monkeypatch.setenv("DOCX_AI_MODELS_STRUCTURE_RECOGNITION_DEFAULT", "gpt-5-mini")
    monkeypatch.setenv("DOCX_AI_MODELS_IMAGE_ANALYSIS_DEFAULT", "gpt-5.4-mini")
    monkeypatch.setenv("DOCX_AI_MODELS_IMAGE_VALIDATION_DEFAULT", "gpt-5-mini")
    monkeypatch.setenv("DOCX_AI_MODELS_IMAGE_RECONSTRUCTION_DEFAULT", "gpt-5.4-mini")
    monkeypatch.setenv("DOCX_AI_MODELS_IMAGE_GENERATION_DEFAULT", "gpt-image-1.5")
    monkeypatch.setenv("DOCX_AI_MODELS_IMAGE_EDIT_DEFAULT", "gpt-image-1.5")
    monkeypatch.setenv("DOCX_AI_MODELS_IMAGE_GENERATION_VISION_DEFAULT", "gpt-5.4-mini")

    app_config = config.load_app_config()
    models = cast(config.ModelRegistry, app_config["models"])

    assert models.text.default == "gpt-5.4"
    assert models.text.options == ("gpt-5.4", "gpt-5.4-mini")
    assert models.structure_recognition == "gpt-5-mini"
    assert models.image_analysis == "gpt-5.4-mini"
    assert models.image_validation == "gpt-5-mini"
    assert models.image_reconstruction == "gpt-5.4-mini"
    assert models.image_generation == "gpt-image-1.5"
    assert models.image_edit == "gpt-image-1.5"
    assert models.image_generation_vision == "gpt-5.4-mini"


def test_load_app_config_rejects_invalid_image_env_value(monkeypatch):
    monkeypatch.setattr(config, "CONFIG_PATH", config.CONFIG_PATH.parent / "__missing_config__.toml")
    monkeypatch.setenv("DOCX_AI_KEEP_ALL_IMAGE_VARIANTS", "sometimes")

    try:
        config.load_app_config()
    except RuntimeError as exc:
        assert "DOCX_AI_KEEP_ALL_IMAGE_VARIANTS" in str(exc)
    else:
        raise AssertionError("Expected RuntimeError for an invalid image bool env override")


def test_load_app_config_rejects_legacy_manual_review_env_alias(monkeypatch):
    monkeypatch.setattr(config, "CONFIG_PATH", config.CONFIG_PATH.parent / "__missing_config__.toml")
    monkeypatch.setenv("DOCX_AI_ENABLE_POST_REDRAW_VALIDATION", "true")

    try:
        config.load_app_config()
    except RuntimeError as exc:
        assert "DOCX_AI_ENABLE_POST_REDRAW_VALIDATION" in str(exc)
    else:
        raise AssertionError("Expected RuntimeError for a removed legacy env alias")


def test_load_app_config_rejects_legacy_manual_review_config_alias(monkeypatch, tmp_path):
    legacy_config = tmp_path / "config.toml"
    legacy_config.write_text('enable_post_redraw_validation = true\n', encoding="utf-8")
    monkeypatch.setattr(config, "CONFIG_PATH", legacy_config)

    try:
        config.load_app_config()
    except RuntimeError as exc:
        assert "enable_post_redraw_validation" in str(exc)
    else:
        raise AssertionError("Expected RuntimeError for a removed legacy config alias")


def test_load_app_config_rejects_invalid_semantic_validation_policy(monkeypatch):
    monkeypatch.setattr(config, "CONFIG_PATH", config.CONFIG_PATH.parent / "__missing_config__.toml")
    monkeypatch.setenv("DOCX_AI_SEMANTIC_VALIDATION_POLICY", "legacy")

    try:
        config.load_app_config()
    except RuntimeError as exc:
        assert "DOCX_AI_SEMANTIC_VALIDATION_POLICY" in str(exc)
    else:
        raise AssertionError("Expected RuntimeError for an invalid semantic validation policy")


def test_load_app_config_output_fonts_default_to_none(monkeypatch):
    monkeypatch.setattr(config, "CONFIG_PATH", config.CONFIG_PATH.parent / "__missing_config__.toml")
    monkeypatch.delenv("DOCX_AI_OUTPUT_BODY_FONT", raising=False)
    monkeypatch.delenv("DOCX_AI_OUTPUT_HEADING_FONT", raising=False)

    app_config = config.load_app_config()

    assert app_config["output_body_font"] is None
    assert app_config["output_heading_font"] is None


def test_load_app_config_output_fonts_from_toml(monkeypatch, tmp_path):
    cfg = tmp_path / "config.toml"
    cfg.write_text(
        '[output.fonts]\nbody = "Times New Roman"\nheading = "Georgia"\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(config, "CONFIG_PATH", cfg)
    monkeypatch.delenv("DOCX_AI_OUTPUT_BODY_FONT", raising=False)
    monkeypatch.delenv("DOCX_AI_OUTPUT_HEADING_FONT", raising=False)

    app_config = config.load_app_config()

    assert app_config["output_body_font"] == "Times New Roman"
    assert app_config["output_heading_font"] == "Georgia"


def test_load_app_config_output_fonts_from_env_override(monkeypatch):
    monkeypatch.setattr(config, "CONFIG_PATH", config.CONFIG_PATH.parent / "__missing_config__.toml")
    monkeypatch.setenv("DOCX_AI_OUTPUT_BODY_FONT", "Arial")
    monkeypatch.setenv("DOCX_AI_OUTPUT_HEADING_FONT", "Arial Bold")

    app_config = config.load_app_config()

    assert app_config["output_body_font"] == "Arial"
    assert app_config["output_heading_font"] == "Arial Bold"


def test_load_app_config_output_fonts_env_overrides_toml(monkeypatch, tmp_path):
    cfg = tmp_path / "config.toml"
    cfg.write_text(
        '[output.fonts]\nbody = "Times New Roman"\nheading = "Georgia"\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(config, "CONFIG_PATH", cfg)
    monkeypatch.setenv("DOCX_AI_OUTPUT_HEADING_FONT", "Wingdings")
    monkeypatch.delenv("DOCX_AI_OUTPUT_BODY_FONT", raising=False)

    app_config = config.load_app_config()

    assert app_config["output_body_font"] == "Times New Roman"   # from toml
    assert app_config["output_heading_font"] == "Wingdings"      # env wins


def test_load_app_config_rejects_invalid_output_fonts_table(monkeypatch, tmp_path):
    cfg = tmp_path / "config.toml"
    cfg.write_text(
        "[output]\nfonts = 123\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(config, "CONFIG_PATH", cfg)
    monkeypatch.delenv("DOCX_AI_OUTPUT_BODY_FONT", raising=False)
    monkeypatch.delenv("DOCX_AI_OUTPUT_HEADING_FONT", raising=False)

    with pytest.raises(RuntimeError, match=r"output\.fonts"):
        config.load_app_config()


def test_get_client_loads_openai_api_key_from_dotenv(monkeypatch, tmp_path):
    dotenv_path = tmp_path / ".env"
    dotenv_path.write_text("OPENAI_API_KEY=test-key-from-dotenv\n", encoding="utf-8")

    captured = {}

    class FakeOpenAI:
        def __init__(self, *, api_key):
            captured["api_key"] = api_key

    monkeypatch.setattr(config, "ENV_PATH", dotenv_path)
    monkeypatch.setattr(config, "OpenAI", FakeOpenAI)
    monkeypatch.setattr(config, "_CLIENT", None)
    monkeypatch.setattr(config, "_CLIENTS_BY_PROVIDER", {})
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    config.get_client()

    assert captured["api_key"] == "test-key-from-dotenv"


def test_get_client_uses_single_locked_initialization(monkeypatch, tmp_path):
    dotenv_path = tmp_path / ".env"
    dotenv_path.write_text("OPENAI_API_KEY=test-key-from-dotenv\n", encoding="utf-8")

    created_instances = []
    constructor_started = threading.Event()
    constructor_release = threading.Event()

    class FakeOpenAI:
        def __init__(self, *, api_key):
            created_instances.append((self, api_key))
            constructor_started.set()
            assert constructor_release.wait(timeout=2)

    monkeypatch.setattr(config, "ENV_PATH", dotenv_path)
    monkeypatch.setattr(config, "OpenAI", FakeOpenAI)
    monkeypatch.setattr(config, "_CLIENT", None)
    monkeypatch.setattr(config, "_CLIENTS_BY_PROVIDER", {})
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    results = []
    errors = []

    def worker() -> None:
        try:
            results.append(config.get_client())
        except Exception as exc:  # pragma: no cover - assertion aid
            errors.append(exc)

    threads = [threading.Thread(target=worker), threading.Thread(target=worker)]
    for thread in threads:
        thread.start()

    assert constructor_started.wait(timeout=2)
    constructor_release.set()

    for thread in threads:
        thread.join(timeout=2)

    assert errors == []
    assert len(results) == 2
    assert results[0] is results[1]
    assert len(created_instances) == 1


def test_get_provider_client_builds_openrouter_client(monkeypatch, tmp_path):
    dotenv_path = tmp_path / ".env"
    dotenv_path.write_text("OPENROUTER_API_KEY=test-openrouter-key\n", encoding="utf-8")

    captured = {}

    class FakeOpenAI:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    provider_registry = config.ProviderRegistry(
        openai=config.ProviderConfig(name="openai", enabled=True, api_key_env="OPENAI_API_KEY"),
        openrouter=config.ProviderConfig(
            name="openrouter",
            enabled=True,
            api_key_env="OPENROUTER_API_KEY",
            base_url="https://openrouter.ai/api/v1",
            referer="DocxAICorrector",
            title="DocxAICorrector",
        ),
    )

    monkeypatch.setattr(config, "ENV_PATH", dotenv_path)
    monkeypatch.setattr(config, "OpenAI", FakeOpenAI)
    monkeypatch.setattr(config, "_CLIENT", None)
    monkeypatch.setattr(config, "_CLIENTS_BY_PROVIDER", {})
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-openrouter-key")

    config.get_provider_client("openrouter", config_like=provider_registry)

    assert captured["api_key"] == "test-openrouter-key"
    assert captured["base_url"] == "https://openrouter.ai/api/v1"
    assert captured["default_headers"] == {
        "HTTP-Referer": "DocxAICorrector",
        "X-OpenRouter-Title": "DocxAICorrector",
    }


def test_load_project_dotenv_overrides_empty_runtime_env_with_repo_value(monkeypatch, tmp_path):
    dotenv_path = tmp_path / ".env"
    dotenv_path.write_text("OPENROUTER_API_KEY=test-openrouter-key\n", encoding="utf-8")

    monkeypatch.setattr(config, "ENV_PATH", dotenv_path)
    monkeypatch.setenv("OPENROUTER_API_KEY", "")

    config.load_project_dotenv()

    assert os.getenv("OPENROUTER_API_KEY") == "test-openrouter-key"


def test_load_project_dotenv_does_not_override_nonempty_runtime_env(monkeypatch, tmp_path):
    # Deploy safety: a real injected secret must win over a stray checked-in .env
    # (precedence environment > .env). Spec 024 / S3.
    dotenv_path = tmp_path / ".env"
    dotenv_path.write_text("OPENAI_API_KEY=dotenv-value\n", encoding="utf-8")

    monkeypatch.setattr(config, "ENV_PATH", dotenv_path)
    monkeypatch.setenv("OPENAI_API_KEY", "real-injected-secret")

    config.load_project_dotenv()

    assert os.getenv("OPENAI_API_KEY") == "real-injected-secret"


def test_load_project_dotenv_is_idempotent_for_set_value(monkeypatch, tmp_path):
    dotenv_path = tmp_path / ".env"
    dotenv_path.write_text("OPENAI_API_KEY=dotenv-value\n", encoding="utf-8")

    monkeypatch.setattr(config, "ENV_PATH", dotenv_path)
    monkeypatch.setenv("OPENAI_API_KEY", "real-injected-secret")

    config.load_project_dotenv()
    config.load_project_dotenv()

    assert os.getenv("OPENAI_API_KEY") == "real-injected-secret"


def _provider_contract_test_args(*, paragraph_boundary_enabled: bool):
    return {
        "model_registry_settings": {
            "models": config.ModelRegistry(
                text=config.TextModelConfig(
                    default="openrouter:google/gemini-3.1-flash-lite-preview",
                    options=("openrouter:google/gemini-3.1-flash-lite-preview", "gpt-5.4-mini"),
                ),
                structure_recognition="openrouter:google/gemini-3.1-flash-lite-preview",
                image_analysis=TEST_IMAGE_ANALYSIS_MODEL,
                image_validation=TEST_IMAGE_VALIDATION_MODEL,
                image_reconstruction=TEST_IMAGE_RECONSTRUCTION_MODEL,
                image_generation=TEST_IMAGE_GENERATION_MODEL,
                image_edit=TEST_IMAGE_EDIT_MODEL,
                image_generation_vision=TEST_IMAGE_GENERATION_VISION_MODEL,
            ),
        },
        "text_runtime_defaults": {
            "audiobook_model": "openrouter:google/gemini-3.1-flash-lite-preview",
        },
        "paragraph_boundary_settings": {
            "paragraph_boundary_ai_review_enabled": paragraph_boundary_enabled,
        },
    }


@pytest.mark.parametrize(
    ("role_name", "paragraph_boundary_enabled"),
    [
        ("paragraph_boundary_ai_review", True),
    ],
)
def test_validate_provider_model_contracts_requires_openai_for_enabled_service_roles_when_provider_disabled(
    monkeypatch,
    role_name,
    paragraph_boundary_enabled,
):
    provider_registry = config.ProviderRegistry(
        openai=config.ProviderConfig(name="openai", enabled=False, api_key_env="OPENAI_API_KEY"),
        openrouter=config.ProviderConfig(name="openrouter", enabled=True, api_key_env="OPENROUTER_API_KEY"),
    )
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    with pytest.raises(RuntimeError, match=rf"OpenAI service role '{role_name}' включён, но provider openai недоступен\."):
        config._validate_provider_model_contracts(
            provider_registry=provider_registry,
            **_provider_contract_test_args(
                paragraph_boundary_enabled=paragraph_boundary_enabled,
            ),
        )


@pytest.mark.parametrize(
    ("role_name", "paragraph_boundary_enabled"),
    [
        ("paragraph_boundary_ai_review", True),
    ],
)
def test_validate_provider_model_contracts_requires_openai_key_for_enabled_service_roles(
    monkeypatch,
    role_name,
    paragraph_boundary_enabled,
):
    provider_registry = config.ProviderRegistry(
        openai=config.ProviderConfig(name="openai", enabled=True, api_key_env="OPENAI_API_KEY"),
        openrouter=config.ProviderConfig(name="openrouter", enabled=True, api_key_env="OPENROUTER_API_KEY"),
    )
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    with pytest.raises(RuntimeError, match=rf"OpenAI service role '{role_name}' включён, но provider openai недоступен\."):
        config._validate_provider_model_contracts(
            provider_registry=provider_registry,
            **_provider_contract_test_args(
                paragraph_boundary_enabled=paragraph_boundary_enabled,
            ),
        )


def test_validate_provider_model_contracts_allows_openrouter_main_text_when_openai_service_role_available(monkeypatch):
    provider_registry = config.ProviderRegistry(
        openai=config.ProviderConfig(name="openai", enabled=True, api_key_env="OPENAI_API_KEY"),
        openrouter=config.ProviderConfig(name="openrouter", enabled=True, api_key_env="OPENROUTER_API_KEY"),
    )
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai")

    config._validate_provider_model_contracts(
        provider_registry=provider_registry,
        model_registry_settings={
            "models": config.ModelRegistry(
                text=config.TextModelConfig(
                    default="openrouter:google/gemini-3.1-flash-lite-preview",
                    options=("openrouter:google/gemini-3.1-flash-lite-preview",),
                ),
                structure_recognition="gpt-5-mini",
                image_analysis=TEST_IMAGE_ANALYSIS_MODEL,
                image_validation=TEST_IMAGE_VALIDATION_MODEL,
                image_reconstruction=TEST_IMAGE_RECONSTRUCTION_MODEL,
                image_generation=TEST_IMAGE_GENERATION_MODEL,
                image_edit=TEST_IMAGE_EDIT_MODEL,
                image_generation_vision=TEST_IMAGE_GENERATION_VISION_MODEL,
            ),
        },
        text_runtime_defaults={
            "audiobook_model": "openrouter:google/gemini-3.1-flash-lite-preview",
        },
        paragraph_boundary_settings={"paragraph_boundary_ai_review_enabled": True},
    )


def test_validate_provider_model_contracts_allows_openrouter_structure_recognition_when_paragraph_ai_review_off(monkeypatch):
    provider_registry = config.ProviderRegistry(
        openai=config.ProviderConfig(name="openai", enabled=True, api_key_env="OPENAI_API_KEY"),
        openrouter=config.ProviderConfig(name="openrouter", enabled=True, api_key_env="OPENROUTER_API_KEY"),
    )
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai")

    config._validate_provider_model_contracts(
        provider_registry=provider_registry,
        model_registry_settings={
            "models": config.ModelRegistry(
                text=config.TextModelConfig(
                    default="openrouter:google/gemini-3.1-flash-lite-preview",
                    options=("openrouter:google/gemini-3.1-flash-lite-preview",),
                ),
                structure_recognition="openrouter:google/gemini-3.1-flash-lite-preview",
                image_analysis=TEST_IMAGE_ANALYSIS_MODEL,
                image_validation=TEST_IMAGE_VALIDATION_MODEL,
                image_reconstruction=TEST_IMAGE_RECONSTRUCTION_MODEL,
                image_generation=TEST_IMAGE_GENERATION_MODEL,
                image_edit=TEST_IMAGE_EDIT_MODEL,
                image_generation_vision=TEST_IMAGE_GENERATION_VISION_MODEL,
            ),
        },
        text_runtime_defaults={
            "audiobook_model": "openrouter:google/gemini-3.1-flash-lite-preview",
        },
        paragraph_boundary_settings={"paragraph_boundary_ai_review_enabled": False},
    )


def test_get_provider_client_cache_is_config_aware(monkeypatch, tmp_path):
    # F16: caching keyed only by provider name returned a stale client when a second
    # call passed a different resolved config (base_url/timeout/headers). The cache must
    # be keyed on the full resolved client fingerprint instead.
    dotenv_path = tmp_path / ".env"
    dotenv_path.write_text("OPENAI_API_KEY=test-key\n", encoding="utf-8")

    created = []

    class FakeOpenAI:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            created.append(self)

    monkeypatch.setattr(config, "ENV_PATH", dotenv_path)
    monkeypatch.setattr(config, "OpenAI", FakeOpenAI)
    monkeypatch.setattr(config, "_CLIENT", None)
    monkeypatch.setattr(config, "_CLIENTS_BY_PROVIDER", {})
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    def _registry(base_url, timeout):
        return config.ProviderRegistry(
            openai=config.ProviderConfig(
                name="openai",
                enabled=True,
                api_key_env="OPENAI_API_KEY",
                base_url=base_url,
                timeout_seconds=timeout,
            ),
            openrouter=config.ProviderConfig(
                name="openrouter", enabled=False, api_key_env="OPENROUTER_API_KEY"
            ),
        )

    registry_a = _registry("https://a.example/v1", 30.0)
    registry_b = _registry("https://b.example/v1", 90.0)

    client_a = config.get_provider_client("openai", config_like=registry_a)
    client_b = config.get_provider_client("openai", config_like=registry_b)

    # Different resolved config => different client instances (no stale reuse).
    assert client_a is not client_b
    assert len(created) == 2

    # Identical config => same cached instance returned.
    client_a_again = config.get_provider_client("openai", config_like=registry_a)
    assert client_a_again is client_a
    assert len(created) == 2
