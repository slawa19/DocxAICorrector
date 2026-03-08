import tomllib

from constants import PROMPTS_DIR


def test_image_prompt_registry_references_existing_non_empty_files():
    registry_path = PROMPTS_DIR / "image_prompt_registry.toml"
    registry = tomllib.loads(registry_path.read_text(encoding="utf-8"))

    expected_keys = {
        "diagram_semantic_redraw",
        "table_semantic_redraw",
        "infographic_semantic_redraw",
        "mindmap_semantic_redraw",
        "chart_semantic_redraw",
        "screenshot_safe_fallback",
        "photo_safe_fallback",
        "mixed_or_ambiguous_fallback",
    }

    assert set(registry["default_prompt_keys"]) == expected_keys
    assert set(registry["prompts"]) == expected_keys

    for prompt_key, prompt_meta in registry["prompts"].items():
        prompt_path = PROMPTS_DIR / prompt_meta["path"]
        assert prompt_path.exists(), f"Prompt file is missing for {prompt_key}"
        assert prompt_path.read_text(encoding="utf-8").strip(), f"Prompt file is empty for {prompt_key}"


def test_image_prompt_registry_has_safety_constraints_for_semantic_and_safe_profiles():
    registry = tomllib.loads((PROMPTS_DIR / "image_prompt_registry.toml").read_text(encoding="utf-8"))

    semantic_prompt_keys = {
        "diagram_semantic_redraw",
        "table_semantic_redraw",
        "infographic_semantic_redraw",
        "mindmap_semantic_redraw",
        "chart_semantic_redraw",
    }
    safe_prompt_keys = {
        "screenshot_safe_fallback",
        "photo_safe_fallback",
        "mixed_or_ambiguous_fallback",
    }

    for prompt_key in semantic_prompt_keys:
        prompt_text = (PROMPTS_DIR / registry["prompts"][prompt_key]["path"]).read_text(encoding="utf-8")
        assert "do not invent" in prompt_text.lower()
        assert "do not remove" in prompt_text.lower()
        assert "preserve" in prompt_text.lower()

    for prompt_key in safe_prompt_keys:
        prompt_text = (PROMPTS_DIR / registry["prompts"][prompt_key]["path"]).read_text(encoding="utf-8")
        assert "safe" in prompt_text.lower() or "original" in prompt_text.lower()
        assert "do not" in prompt_text.lower()
