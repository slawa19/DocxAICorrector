import os
import tomllib

import pypandoc
from openai import OpenAI

from constants import (
    CONFIG_PATH,
    DEFAULT_CHUNK_SIZE,
    DEFAULT_MAX_RETRIES,
    DEFAULT_MODEL,
    DEFAULT_MODEL_OPTIONS,
    SYSTEM_PROMPT_PATH,
)


def parse_int_env(name: str, default: int) -> int:
    raw_value = os.getenv(name, "").strip()
    if not raw_value:
        return default
    try:
        return int(raw_value)
    except ValueError as exc:
        raise RuntimeError(f"Некорректное целое значение в {name}: {raw_value}") from exc


def parse_csv_env(name: str) -> list[str] | None:
    raw_value = os.getenv(name, "").strip()
    if not raw_value:
        return None
    items = [item.strip() for item in raw_value.split(",") if item.strip()]
    if not items:
        raise RuntimeError(f"Переменная {name} задана, но список моделей пуст.")
    return items


def load_app_config() -> dict[str, object]:
    config_data: dict[str, object] = {}
    if CONFIG_PATH.exists():
        with CONFIG_PATH.open("rb") as file_handle:
            config_data = tomllib.load(file_handle)

    model_options = config_data.get("model_options", DEFAULT_MODEL_OPTIONS)
    if not isinstance(model_options, list) or not all(isinstance(item, str) and item.strip() for item in model_options):
        raise RuntimeError(f"Некорректное поле model_options в {CONFIG_PATH}")

    default_model = config_data.get("default_model", DEFAULT_MODEL)
    if not isinstance(default_model, str) or not default_model.strip():
        raise RuntimeError(f"Некорректное поле default_model в {CONFIG_PATH}")

    chunk_size = config_data.get("chunk_size", DEFAULT_CHUNK_SIZE)
    if not isinstance(chunk_size, int):
        raise RuntimeError(f"Некорректное поле chunk_size в {CONFIG_PATH}")

    max_retries = config_data.get("max_retries", DEFAULT_MAX_RETRIES)
    if not isinstance(max_retries, int):
        raise RuntimeError(f"Некорректное поле max_retries в {CONFIG_PATH}")

    env_model_options = parse_csv_env("DOCX_AI_MODEL_OPTIONS")
    if env_model_options is not None:
        model_options = env_model_options

    default_model = os.getenv("DOCX_AI_DEFAULT_MODEL", default_model).strip() or default_model
    chunk_size = parse_int_env("DOCX_AI_CHUNK_SIZE", chunk_size)
    max_retries = parse_int_env("DOCX_AI_MAX_RETRIES", max_retries)

    if default_model not in model_options:
        model_options = [default_model, *[item for item in model_options if item != default_model]]

    return {
        "default_model": default_model,
        "model_options": model_options,
        "chunk_size": max(3000, min(chunk_size, 12000)),
        "max_retries": max(1, min(max_retries, 5)),
    }


def load_system_prompt() -> str:
    try:
        prompt_text = SYSTEM_PROMPT_PATH.read_text(encoding="utf-8").strip()
    except FileNotFoundError as exc:
        raise RuntimeError(f"Не найден файл системного промпта: {SYSTEM_PROMPT_PATH}") from exc

    if not prompt_text:
        raise RuntimeError(f"Файл системного промпта пуст: {SYSTEM_PROMPT_PATH}")

    return prompt_text


def get_client() -> OpenAI:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("Не найден OPENAI_API_KEY. Добавьте его в .env или переменные окружения.")
    return OpenAI(api_key=api_key)


def ensure_pandoc_available() -> None:
    try:
        pypandoc.get_pandoc_version()
    except OSError as exc:
        raise RuntimeError(
            "Pandoc не найден. Для Windows PowerShell установите его командой: "
            "winget install --id JohnMacFarlane.Pandoc -e"
        ) from exc
