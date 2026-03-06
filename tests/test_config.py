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


def test_parse_csv_env_rejects_empty_effective_list(monkeypatch):
    monkeypatch.setenv("DOCX_AI_MODEL_OPTIONS", " , , ")

    try:
        config.parse_csv_env("DOCX_AI_MODEL_OPTIONS")
    except RuntimeError as exc:
        assert "список моделей пуст" in str(exc)
    else:
        raise AssertionError("Expected RuntimeError for an empty CSV env override")