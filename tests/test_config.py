import pytest

import config


def test_load_app_config_applies_env_overrides_and_clamps(monkeypatch):
    monkeypatch.setattr(config, "CONFIG_PATH", config.CONFIG_PATH.parent / "__missing_config__.toml")
    monkeypatch.setenv("DOCX_AI_MODEL_OPTIONS", "gpt-5.4, custom-model")
    monkeypatch.setenv("DOCX_AI_DEFAULT_MODEL", "gpt-5.1")
    monkeypatch.setenv("DOCX_AI_CHUNK_SIZE", "20000")
    monkeypatch.setenv("DOCX_AI_MAX_RETRIES", "0")

    app_config = config.load_app_config()

    assert app_config["default_model"] == "gpt-5.1"
    assert app_config["model_options"] == ["gpt-5.1", "gpt-5.4", "custom-model"]
    assert app_config["chunk_size"] == 12000
    assert app_config["max_retries"] == 1
    assert app_config["enable_paragraph_markers"] is False


def test_load_app_config_exposes_image_validation_defaults(monkeypatch):
    monkeypatch.setattr(config, "CONFIG_PATH", config.CONFIG_PATH)

    app_config = config.load_app_config()

    assert app_config["enable_paragraph_markers"] is True
    assert app_config["image_mode_default"] == "no_change"
    assert app_config["semantic_validation_policy"] == "advisory"
    assert app_config["keep_all_image_variants"] is False
    assert app_config["validation_model"] == "gpt-4.1"
    assert app_config["min_semantic_match_score"] == 0.75
    assert app_config["min_text_match_score"] == 0.8
    assert app_config["min_structure_match_score"] == 0.7
    assert app_config["validator_confidence_threshold"] == 0.75
    assert app_config["allow_accept_with_partial_text_loss"] is False
    assert app_config["prefer_deterministic_reconstruction"] is True
    assert app_config["reconstruction_model"] == "gpt-4.1"
    assert app_config["enable_vision_image_analysis"] is True
    assert app_config["enable_vision_image_validation"] is True
    assert app_config["semantic_redraw_max_attempts"] == 2
    assert app_config["semantic_redraw_max_model_calls_per_image"] == 9
    assert app_config["dense_text_bypass_threshold"] == 18
    assert app_config["non_latin_text_bypass_threshold"] == 12
    assert app_config["reconstruction_min_canvas_short_side_px"] == 900
    assert app_config["reconstruction_target_min_font_px"] == 18
    assert app_config["reconstruction_max_upscale_factor"] == 3.0


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
    monkeypatch.setenv("DOCX_AI_RECONSTRUCTION_MODEL", "gpt-4.1-mini")
    monkeypatch.setenv("DOCX_AI_ENABLE_VISION_IMAGE_ANALYSIS", "false")
    monkeypatch.setenv("DOCX_AI_ENABLE_VISION_IMAGE_VALIDATION", "false")
    monkeypatch.setenv("DOCX_AI_SEMANTIC_REDRAW_MAX_ATTEMPTS", "9")
    monkeypatch.setenv("DOCX_AI_SEMANTIC_REDRAW_MAX_MODEL_CALLS_PER_IMAGE", "99")
    monkeypatch.setenv("DOCX_AI_DENSE_TEXT_BYPASS_THRESHOLD", "99")
    monkeypatch.setenv("DOCX_AI_NON_LATIN_TEXT_BYPASS_THRESHOLD", "77")
    monkeypatch.setenv("DOCX_AI_RECONSTRUCTION_MIN_CANVAS_SHORT_SIDE_PX", "8192")
    monkeypatch.setenv("DOCX_AI_RECONSTRUCTION_TARGET_MIN_FONT_PX", "8")
    monkeypatch.setenv("DOCX_AI_RECONSTRUCTION_MAX_UPSCALE_FACTOR", "9")

    app_config = config.load_app_config()

    assert app_config["image_mode_default"] == "semantic_redraw_direct"
    assert app_config["semantic_validation_policy"] == "strict"
    assert app_config["keep_all_image_variants"] is True
    assert app_config["validation_model"] == "gpt-5.4"
    assert app_config["min_semantic_match_score"] == 1.0
    assert app_config["min_text_match_score"] == 0.0
    assert app_config["min_structure_match_score"] == 0.91
    assert app_config["validator_confidence_threshold"] == 1.0
    assert app_config["allow_accept_with_partial_text_loss"] is True
    assert app_config["prefer_deterministic_reconstruction"] is False
    assert app_config["enable_paragraph_markers"] is True
    assert app_config["reconstruction_model"] == "gpt-4.1-mini"
    assert app_config["enable_vision_image_analysis"] is False
    assert app_config["enable_vision_image_validation"] is False
    assert app_config["semantic_redraw_max_attempts"] == 2
    assert app_config["semantic_redraw_max_model_calls_per_image"] == 20
    assert app_config["dense_text_bypass_threshold"] == 80
    assert app_config["non_latin_text_bypass_threshold"] == 77
    assert app_config["reconstruction_min_canvas_short_side_px"] == 4096
    assert app_config["reconstruction_target_min_font_px"] == 10
    assert app_config["reconstruction_max_upscale_factor"] == 6.0


def test_parse_csv_env_rejects_empty_effective_list(monkeypatch):
    monkeypatch.setenv("DOCX_AI_MODEL_OPTIONS", " , , ")

    try:
        config.parse_csv_env("DOCX_AI_MODEL_OPTIONS")
    except RuntimeError as exc:
        assert "список моделей пуст" in str(exc)
    else:
        raise AssertionError("Expected RuntimeError for an empty CSV env override")


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
