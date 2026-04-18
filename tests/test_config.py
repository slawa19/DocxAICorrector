import threading
from typing import cast

import pytest

import config
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
    supported_languages = cast(list[config.LanguageOption], app_config["supported_languages"])
    assert supported_languages[0].code == "ru"
    assert app_config["enable_paragraph_markers"] is False
    assert app_config["paragraph_boundary_normalization_enabled"] is True
    assert app_config["paragraph_boundary_normalization_mode"] == "high_only"
    assert app_config["paragraph_boundary_normalization_save_debug_artifacts"] is True
    assert app_config["structure_recognition_enabled"] is False
    assert app_config["structure_recognition_model"] == TEST_STRUCTURE_RECOGNITION_MODEL
    assert models.structure_recognition == TEST_STRUCTURE_RECOGNITION_MODEL
    assert app_config["structure_recognition_max_window_paragraphs"] == 1800
    assert app_config["structure_recognition_overlap_paragraphs"] == 50
    assert app_config["structure_recognition_timeout_seconds"] == 60
    assert app_config["structure_recognition_min_confidence"] == "medium"
    assert app_config["structure_recognition_cache_enabled"] is True
    assert app_config["structure_recognition_save_debug_artifacts"] is True
    assert app_config["relation_normalization_enabled"] is True
    assert app_config["relation_normalization_profile"] == "phase2_default"
    assert app_config["relation_normalization_enabled_relation_kinds"] == (
        "image_caption",
        "table_caption",
        "epigraph_attribution",
        "toc_region",
    )
    assert app_config["relation_normalization_save_debug_artifacts"] is True


def test_load_app_config_exposes_image_validation_defaults(monkeypatch):
    monkeypatch.setattr(config, "CONFIG_PATH", config.CONFIG_PATH)

    app_config = config.load_app_config()
    models = cast(config.ModelRegistry, app_config["models"])

    assert app_config["enable_paragraph_markers"] is True
    assert app_config["processing_operation_default"] == "edit"
    assert app_config["source_language_default"] == "en"
    assert app_config["target_language_default"] == "ru"
    assert app_config["editorial_intensity_default"] == "literary"
    supported_languages = cast(list[config.LanguageOption], app_config["supported_languages"])
    assert [language.code for language in supported_languages] == ["ru", "en", "de", "fr", "es", "it", "pl", "zh", "ja"]
    assert app_config["paragraph_boundary_normalization_enabled"] is True
    assert app_config["paragraph_boundary_normalization_mode"] == "high_only"
    assert app_config["paragraph_boundary_normalization_save_debug_artifacts"] is True
    assert app_config["structure_recognition_enabled"] is False
    assert app_config["structure_recognition_model"] == TEST_STRUCTURE_RECOGNITION_MODEL
    assert models.text.default == TEST_TEXT_MODEL_DEFAULT
    assert models.text.options == ("gpt-5.4", "gpt-5.4-mini", "gpt-5-mini")
    assert models.structure_recognition == TEST_STRUCTURE_RECOGNITION_MODEL
    assert app_config["structure_recognition_max_window_paragraphs"] == 1800
    assert app_config["structure_recognition_overlap_paragraphs"] == 50
    assert app_config["structure_recognition_timeout_seconds"] == 60
    assert app_config["structure_recognition_min_confidence"] == "medium"
    assert app_config["structure_recognition_cache_enabled"] is True
    assert app_config["structure_recognition_save_debug_artifacts"] is True
    assert app_config["relation_normalization_enabled"] is True
    assert app_config["relation_normalization_profile"] == "phase2_default"
    assert app_config["relation_normalization_enabled_relation_kinds"] == (
        "image_caption",
        "table_caption",
        "epigraph_attribution",
        "toc_region",
    )
    assert app_config["relation_normalization_save_debug_artifacts"] is True
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


def test_load_system_prompt_translate_includes_hardening_rules():
    config.load_system_prompt.cache_clear()
    try:
        prompt = config.load_system_prompt(operation="translate", source_language="en", target_language="ru")
    finally:
        config.load_system_prompt.cache_clear()

    assert "не выполняйте повторный перевод" in prompt
    assert "ориентируйтесь в первую очередь на фактический язык блока" in prompt
    assert "предпочитайте консервативный результат" in prompt


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


def test_load_app_config_applies_structure_recognition_env_overrides(monkeypatch):
    monkeypatch.setattr(config, "CONFIG_PATH", config.CONFIG_PATH.parent / "__missing_config__.toml")
    monkeypatch.setenv("DOCX_AI_STRUCTURE_RECOGNITION_ENABLED", "true")
    monkeypatch.setenv("DOCX_AI_STRUCTURE_RECOGNITION_MODEL", "gpt-5.4")
    monkeypatch.setenv("DOCX_AI_STRUCTURE_RECOGNITION_MAX_WINDOW_PARAGRAPHS", "9999")
    monkeypatch.setenv("DOCX_AI_STRUCTURE_RECOGNITION_OVERLAP_PARAGRAPHS", "999")
    monkeypatch.setenv("DOCX_AI_STRUCTURE_RECOGNITION_TIMEOUT_SECONDS", "999")
    monkeypatch.setenv("DOCX_AI_STRUCTURE_RECOGNITION_MIN_CONFIDENCE", "high")
    monkeypatch.setenv("DOCX_AI_STRUCTURE_RECOGNITION_CACHE_ENABLED", "false")
    monkeypatch.setenv("DOCX_AI_STRUCTURE_RECOGNITION_SAVE_DEBUG_ARTIFACTS", "false")

    app_config = config.load_app_config()
    models = cast(config.ModelRegistry, app_config["models"])

    assert app_config["structure_recognition_enabled"] is True
    assert app_config["structure_recognition_model"] == "gpt-5.4"
    assert models.structure_recognition == "gpt-5.4"
    assert app_config["structure_recognition_max_window_paragraphs"] == 4000
    assert app_config["structure_recognition_overlap_paragraphs"] == 200
    assert app_config["structure_recognition_timeout_seconds"] == 300
    assert app_config["structure_recognition_min_confidence"] == "high"
    assert app_config["structure_recognition_cache_enabled"] is False
    assert app_config["structure_recognition_save_debug_artifacts"] is False


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
