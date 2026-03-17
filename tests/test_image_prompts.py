import tomllib
from typing import Any

import pytest

from constants import PROMPTS_DIR
import image_prompts

PRESERVATION_VARIANTS = ("preserve", "keep the same")
ANTI_HALLUCINATION_VARIANTS = ("do not invent", "avoid guessing", "avoid hallucinating")
NO_REMOVAL_VARIANTS = ("do not remove", "do not collapse", "do not merge")
SAFE_PRESERVATION_VARIANTS = ("safe", "original", "preserve")
SAFE_RESTRICTION_VARIANTS = ("do not", "preserve the original image without modification")


def _read_registry() -> dict[str, Any]:
    return tomllib.loads((PROMPTS_DIR / "image_prompt_registry.toml").read_text(encoding="utf-8"))


def _contains_any(text: str, variants: tuple[str, ...]) -> bool:
    lowered = text.lower()
    return any(variant in lowered for variant in variants)


def _write_registry(tmp_path, monkeypatch, registry_text: str) -> None:
    monkeypatch.setattr(image_prompts, "PROMPTS_DIR", tmp_path)
    image_prompts.load_image_prompt_registry.cache_clear()
    (tmp_path / "image_prompt_registry.toml").write_text(registry_text, encoding="utf-8")


@pytest.fixture(autouse=True)
def clear_prompt_registry_cache():
    image_prompts.load_image_prompt_registry.cache_clear()
    yield
    image_prompts.load_image_prompt_registry.cache_clear()


def test_image_prompt_registry_references_existing_non_empty_files():
    registry = _read_registry()

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

    registry_keys = set(registry["prompts"])
    assert set(registry["default_prompt_keys"]) == expected_keys
    assert registry_keys == expected_keys

    for prompt_key, prompt_meta in registry["prompts"].items():
        prompt_path = PROMPTS_DIR / prompt_meta["path"]
        assert prompt_path.exists(), f"Prompt file is missing for {prompt_key}"
        assert prompt_path.read_text(encoding="utf-8").strip(), f"Prompt file is empty for {prompt_key}"


def test_safety_constraints_in_prompt_profiles():
    registry = _read_registry()

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
        assert _contains_any(
            prompt_text,
            PRESERVATION_VARIANTS,
        ), f"{prompt_key} is missing a preservation constraint"
        assert _contains_any(
            prompt_text,
            ANTI_HALLUCINATION_VARIANTS,
        ), f"{prompt_key} is missing an anti-hallucination constraint"
        assert _contains_any(
            prompt_text,
            NO_REMOVAL_VARIANTS,
        ), f"{prompt_key} is missing a no-removal/no-collapse constraint"

    for prompt_key in safe_prompt_keys:
        prompt_text = (PROMPTS_DIR / registry["prompts"][prompt_key]["path"]).read_text(encoding="utf-8")
        assert _contains_any(
            prompt_text,
            SAFE_PRESERVATION_VARIANTS,
        ), f"{prompt_key} is missing a safe-preservation signal"
        assert _contains_any(
            prompt_text,
            SAFE_RESTRICTION_VARIANTS,
        ), f"{prompt_key} is missing a restriction against unsafe transformation"


def test_load_image_prompt_registry_rejects_invalid_toml(tmp_path, monkeypatch):
    _write_registry(tmp_path, monkeypatch, "[prompts\ninvalid = true")

    with pytest.raises(RuntimeError, match="Некорректный TOML registry image prompt-профилей"):
        image_prompts.load_image_prompt_registry()


def test_load_image_prompt_registry_rejects_missing_prompts_section(tmp_path, monkeypatch):
    _write_registry(tmp_path, monkeypatch, "default_prompt_keys = ['demo']")

    with pytest.raises(RuntimeError, match="Некорректный registry image prompt-профилей"):
        image_prompts.load_image_prompt_registry()


def test_get_image_prompt_profile_rejects_invalid_profile_structure(tmp_path, monkeypatch):
    _write_registry(
        tmp_path,
        monkeypatch,
        """
        [prompts.demo]
        path = "demo.txt"
        preferred_strategy = ""
        description = "Demo"
        """,
    )

    with pytest.raises(RuntimeError, match="Некорректное описание image prompt profile: demo"):
        image_prompts.get_image_prompt_profile("demo")


def test_get_image_prompt_profile_rejects_missing_prompt_file(tmp_path, monkeypatch):
    _write_registry(
        tmp_path,
        monkeypatch,
        """
        [prompts.demo]
        path = "missing.txt"
        preferred_strategy = "safe"
        description = "Demo"
        """,
    )

    with pytest.raises(RuntimeError, match="Не найден image prompt file для demo"):
        image_prompts.get_image_prompt_profile("demo")
