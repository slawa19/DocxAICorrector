import os
import tomllib

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


def parse_bool_env(name: str, default: bool) -> bool:
    raw_value = os.getenv(name, "").strip().lower()
    if not raw_value:
        return default
    if raw_value in {"1", "true", "yes", "on"}:
        return True
    if raw_value in {"0", "false", "no", "off"}:
        return False
    raise RuntimeError(f"Некорректное булево значение в {name}: {raw_value}")


def parse_float_env(name: str, default: float) -> float:
    raw_value = os.getenv(name, "").strip()
    if not raw_value:
        return default
    try:
        return float(raw_value)
    except ValueError as exc:
        raise RuntimeError(f"Некорректное число в {name}: {raw_value}") from exc


def clamp_score(value: float) -> float:
    return max(0.0, min(float(value), 1.0))


def parse_config_bool(config_data: dict[str, object], field_name: str, default: bool) -> bool:
    value = config_data.get(field_name, default)
    if not isinstance(value, bool):
        raise RuntimeError(f"Некорректное поле {field_name} в {CONFIG_PATH}")
    return value


def parse_config_str(config_data: dict[str, object], field_name: str, default: str) -> str:
    value = config_data.get(field_name, default)
    if not isinstance(value, str) or not value.strip():
        raise RuntimeError(f"Некорректное поле {field_name} в {CONFIG_PATH}")
    return value


def parse_config_score(config_data: dict[str, object], field_name: str, default: float) -> float:
    value = config_data.get(field_name, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise RuntimeError(f"Некорректное поле {field_name} в {CONFIG_PATH}")
    return clamp_score(float(value))


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

    image_mode_default = parse_config_str(config_data, "image_mode_default", "safe")
    enable_post_redraw_validation = parse_config_bool(config_data, "enable_post_redraw_validation", True)
    validation_model = parse_config_str(config_data, "validation_model", "gpt-4.1")
    min_semantic_match_score = parse_config_score(config_data, "min_semantic_match_score", 0.75)
    min_text_match_score = parse_config_score(config_data, "min_text_match_score", 0.80)
    min_structure_match_score = parse_config_score(config_data, "min_structure_match_score", 0.70)
    validator_confidence_threshold = parse_config_score(config_data, "validator_confidence_threshold", 0.75)
    allow_accept_with_partial_text_loss = parse_config_bool(
        config_data,
        "allow_accept_with_partial_text_loss",
        False,
    )
    prefer_structured_redraw = parse_config_bool(config_data, "prefer_structured_redraw", True)

    env_model_options = parse_csv_env("DOCX_AI_MODEL_OPTIONS")
    if env_model_options is not None:
        model_options = env_model_options

    default_model = os.getenv("DOCX_AI_DEFAULT_MODEL", default_model).strip() or default_model
    chunk_size = parse_int_env("DOCX_AI_CHUNK_SIZE", chunk_size)
    max_retries = parse_int_env("DOCX_AI_MAX_RETRIES", max_retries)
    image_mode_default = os.getenv("DOCX_AI_IMAGE_MODE_DEFAULT", image_mode_default).strip() or image_mode_default
    enable_post_redraw_validation = parse_bool_env(
        "DOCX_AI_ENABLE_POST_REDRAW_VALIDATION",
        enable_post_redraw_validation,
    )
    validation_model = os.getenv("DOCX_AI_VALIDATION_MODEL", validation_model).strip() or validation_model
    min_semantic_match_score = clamp_score(
        parse_float_env("DOCX_AI_MIN_SEMANTIC_MATCH_SCORE", min_semantic_match_score)
    )
    min_text_match_score = clamp_score(parse_float_env("DOCX_AI_MIN_TEXT_MATCH_SCORE", min_text_match_score))
    min_structure_match_score = clamp_score(
        parse_float_env("DOCX_AI_MIN_STRUCTURE_MATCH_SCORE", min_structure_match_score)
    )
    validator_confidence_threshold = clamp_score(
        parse_float_env("DOCX_AI_VALIDATOR_CONFIDENCE_THRESHOLD", validator_confidence_threshold)
    )
    allow_accept_with_partial_text_loss = parse_bool_env(
        "DOCX_AI_ALLOW_ACCEPT_WITH_PARTIAL_TEXT_LOSS",
        allow_accept_with_partial_text_loss,
    )

    if default_model not in model_options:
        model_options = [default_model, *[item for item in model_options if item != default_model]]

    return {
        "default_model": default_model,
        "model_options": model_options,
        "chunk_size": max(3000, min(chunk_size, 12000)),
        "max_retries": max(1, min(max_retries, 5)),
        "image_mode_default": image_mode_default,
        "enable_post_redraw_validation": enable_post_redraw_validation,
        "validation_model": validation_model,
        "min_semantic_match_score": min_semantic_match_score,
        "min_text_match_score": min_text_match_score,
        "min_structure_match_score": min_structure_match_score,
        "validator_confidence_threshold": validator_confidence_threshold,
        "allow_accept_with_partial_text_loss": allow_accept_with_partial_text_loss,
        "prefer_structured_redraw": prefer_structured_redraw,
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
