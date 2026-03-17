from functools import lru_cache
from pathlib import Path
import tomllib

from constants import PROMPTS_DIR


@lru_cache(maxsize=1)
def load_image_prompt_registry() -> dict[str, object]:
    registry_path = PROMPTS_DIR / "image_prompt_registry.toml"
    try:
        registry = tomllib.loads(registry_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise RuntimeError(f"Не найден registry image prompt-профилей: {registry_path}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise RuntimeError(f"Некорректный TOML registry image prompt-профилей: {registry_path}") from exc

    prompts = registry.get("prompts")
    if not isinstance(prompts, dict) or not prompts:
        raise RuntimeError(f"Некорректный registry image prompt-профилей: {registry_path}")
    return registry


def get_image_prompt_profile(prompt_key: str) -> dict[str, str]:
    registry = load_image_prompt_registry()
    prompt_meta = registry["prompts"].get(prompt_key)
    if not isinstance(prompt_meta, dict):
        raise RuntimeError(f"Не найден image prompt profile: {prompt_key}")

    path = prompt_meta.get("path")
    preferred_strategy = prompt_meta.get("preferred_strategy")
    description = prompt_meta.get("description")
    if not all(isinstance(value, str) and value.strip() for value in (path, preferred_strategy, description)):
        raise RuntimeError(f"Некорректное описание image prompt profile: {prompt_key}")

    prompt_path = PROMPTS_DIR / path
    if not prompt_path.exists():
        raise RuntimeError(f"Не найден image prompt file для {prompt_key}: {prompt_path}")

    return {"path": str(prompt_path), "preferred_strategy": preferred_strategy, "description": description}


def load_image_prompt_text(prompt_key: str) -> str:
    prompt_profile = get_image_prompt_profile(prompt_key)
    prompt_text = Path(prompt_profile["path"]).read_text(encoding="utf-8").strip()
    if not prompt_text:
        raise RuntimeError(f"Пустой image prompt file для {prompt_key}: {prompt_profile['path']}")
    return prompt_text
