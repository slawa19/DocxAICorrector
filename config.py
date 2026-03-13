import os
import tomllib
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING

from dotenv import load_dotenv

from constants import (
    CONFIG_PATH,
    DEFAULT_CHUNK_SIZE,
    DEFAULT_MAX_RETRIES,
    DEFAULT_MODEL,
    DEFAULT_MODEL_OPTIONS,
    ENV_PATH,
    SYSTEM_PROMPT_PATH,
)
from image_shared import clamp_score
from models import IMAGE_MODE_VALUES, ImageMode

try:
    from openai import OpenAI
except Exception:  # pragma: no cover - import is validated via get_client/test seams
    OpenAI = None

if TYPE_CHECKING:
    from openai import OpenAI


@dataclass(frozen=True)
class AppConfig(Mapping[str, object]):
    default_model: str
    model_options: list[str]
    chunk_size: int
    max_retries: int
    image_mode_default: str
    semantic_validation_policy: str
    enable_post_redraw_validation: bool
    validation_model: str
    min_semantic_match_score: float
    min_text_match_score: float
    min_structure_match_score: float
    validator_confidence_threshold: float
    allow_accept_with_partial_text_loss: bool
    prefer_deterministic_reconstruction: bool
    reconstruction_model: str
    enable_vision_image_analysis: bool
    enable_vision_image_validation: bool
    semantic_redraw_max_attempts: int
    semantic_redraw_max_model_calls_per_image: int
    dense_text_bypass_threshold: int
    non_latin_text_bypass_threshold: int
    reconstruction_min_canvas_short_side_px: int
    reconstruction_target_min_font_px: int
    reconstruction_max_upscale_factor: float
    reconstruction_background_sample_ratio: float
    reconstruction_background_color_distance_threshold: float
    reconstruction_background_uniformity_threshold: float

    def __getitem__(self, key: str) -> object:
        return getattr(self, key)

    def __iter__(self) -> Iterator[str]:
        return iter(self.__dataclass_fields__)

    def __len__(self) -> int:
        return len(self.__dataclass_fields__)

    def to_dict(self) -> dict[str, object]:
        return {field_name: getattr(self, field_name) for field_name in self}


def _parse_image_mode(value: str, *, source_name: str) -> str:
    normalized = value.strip().lower()
    if normalized not in IMAGE_MODE_VALUES:
        raise RuntimeError(f"Некорректное значение image_mode в {source_name}: {value}")
    return ImageMode(normalized).value


def load_project_dotenv() -> None:
    load_dotenv(dotenv_path=ENV_PATH, override=False)


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


def parse_choice_str(config_data: dict[str, object], field_name: str, default: str, allowed_values: set[str]) -> str:
    value = parse_config_str(config_data, field_name, default).strip().lower()
    if value not in allowed_values:
        raise RuntimeError(f"Некорректное поле {field_name} в {CONFIG_PATH}")
    return value


def parse_config_score(config_data: dict[str, object], field_name: str, default: float) -> float:
    value = config_data.get(field_name, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise RuntimeError(f"Некорректное поле {field_name} в {CONFIG_PATH}")
    return clamp_score(float(value))


def parse_config_float(config_data: dict[str, object], field_name: str, default: float) -> float:
    value = config_data.get(field_name, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise RuntimeError(f"Некорректное поле {field_name} в {CONFIG_PATH}")
    return float(value)


def parse_config_int(config_data: dict[str, object], field_name: str, default: int) -> int:
    value = config_data.get(field_name, default)
    if isinstance(value, bool) or not isinstance(value, int):
        raise RuntimeError(f"Некорректное поле {field_name} в {CONFIG_PATH}")
    return value


def load_app_config() -> AppConfig:
    load_project_dotenv()
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

    image_mode_default = _parse_image_mode(
        parse_config_str(config_data, "image_mode_default", ImageMode.SAFE.value),
        source_name=str(CONFIG_PATH),
    )
    semantic_validation_policy = parse_choice_str(
        config_data,
        "semantic_validation_policy",
        "advisory",
        {"advisory", "strict"},
    )
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
    prefer_deterministic_reconstruction = parse_config_bool(
        config_data, "prefer_deterministic_reconstruction", True
    )
    reconstruction_model = parse_config_str(config_data, "reconstruction_model", "gpt-4.1")
    enable_vision_image_analysis = parse_config_bool(config_data, "enable_vision_image_analysis", True)
    enable_vision_image_validation = parse_config_bool(config_data, "enable_vision_image_validation", True)
    semantic_redraw_max_attempts = parse_config_int(config_data, "semantic_redraw_max_attempts", 3)
    semantic_redraw_max_model_calls_per_image = parse_config_int(
        config_data,
        "semantic_redraw_max_model_calls_per_image",
        semantic_redraw_max_attempts * 3,
    )
    dense_text_bypass_threshold = parse_config_int(config_data, "dense_text_bypass_threshold", 18)
    non_latin_text_bypass_threshold = parse_config_int(config_data, "non_latin_text_bypass_threshold", 12)
    reconstruction_min_canvas_short_side_px = parse_config_int(
        config_data,
        "reconstruction_min_canvas_short_side_px",
        900,
    )
    reconstruction_target_min_font_px = parse_config_int(config_data, "reconstruction_target_min_font_px", 18)
    reconstruction_max_upscale_factor = parse_config_float(config_data, "reconstruction_max_upscale_factor", 3.0)
    reconstruction_background_sample_ratio = parse_config_float(
        config_data,
        "reconstruction_background_sample_ratio",
        0.04,
    )
    reconstruction_background_color_distance_threshold = parse_config_float(
        config_data,
        "reconstruction_background_color_distance_threshold",
        48.0,
    )
    reconstruction_background_uniformity_threshold = parse_config_float(
        config_data,
        "reconstruction_background_uniformity_threshold",
        10.0,
    )

    env_model_options = parse_csv_env("DOCX_AI_MODEL_OPTIONS")
    if env_model_options is not None:
        model_options = env_model_options

    default_model = os.getenv("DOCX_AI_DEFAULT_MODEL", default_model).strip() or default_model
    chunk_size = parse_int_env("DOCX_AI_CHUNK_SIZE", chunk_size)
    max_retries = parse_int_env("DOCX_AI_MAX_RETRIES", max_retries)
    image_mode_default = _parse_image_mode(
        os.getenv("DOCX_AI_IMAGE_MODE_DEFAULT", image_mode_default).strip() or image_mode_default,
        source_name="DOCX_AI_IMAGE_MODE_DEFAULT",
    )
    enable_post_redraw_validation = parse_bool_env(
        "DOCX_AI_ENABLE_POST_REDRAW_VALIDATION",
        enable_post_redraw_validation,
    )
    semantic_validation_policy = os.getenv(
        "DOCX_AI_SEMANTIC_VALIDATION_POLICY",
        semantic_validation_policy,
    ).strip().lower() or semantic_validation_policy
    if semantic_validation_policy not in {"advisory", "strict"}:
        raise RuntimeError(
            f"Некорректное значение в DOCX_AI_SEMANTIC_VALIDATION_POLICY: {semantic_validation_policy}"
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
    prefer_deterministic_reconstruction = parse_bool_env(
        "DOCX_AI_PREFER_DETERMINISTIC_RECONSTRUCTION",
        prefer_deterministic_reconstruction,
    )
    reconstruction_model = os.getenv("DOCX_AI_RECONSTRUCTION_MODEL", reconstruction_model).strip() or reconstruction_model
    enable_vision_image_analysis = parse_bool_env(
        "DOCX_AI_ENABLE_VISION_IMAGE_ANALYSIS",
        enable_vision_image_analysis,
    )
    enable_vision_image_validation = parse_bool_env(
        "DOCX_AI_ENABLE_VISION_IMAGE_VALIDATION",
        enable_vision_image_validation,
    )
    semantic_redraw_max_attempts = parse_int_env(
        "DOCX_AI_SEMANTIC_REDRAW_MAX_ATTEMPTS",
        semantic_redraw_max_attempts,
    )
    semantic_redraw_max_model_calls_per_image = parse_int_env(
        "DOCX_AI_SEMANTIC_REDRAW_MAX_MODEL_CALLS_PER_IMAGE",
        semantic_redraw_max_model_calls_per_image,
    )
    dense_text_bypass_threshold = parse_int_env(
        "DOCX_AI_DENSE_TEXT_BYPASS_THRESHOLD",
        dense_text_bypass_threshold,
    )
    non_latin_text_bypass_threshold = parse_int_env(
        "DOCX_AI_NON_LATIN_TEXT_BYPASS_THRESHOLD",
        non_latin_text_bypass_threshold,
    )
    reconstruction_min_canvas_short_side_px = parse_int_env(
        "DOCX_AI_RECONSTRUCTION_MIN_CANVAS_SHORT_SIDE_PX",
        reconstruction_min_canvas_short_side_px,
    )
    reconstruction_target_min_font_px = parse_int_env(
        "DOCX_AI_RECONSTRUCTION_TARGET_MIN_FONT_PX",
        reconstruction_target_min_font_px,
    )
    reconstruction_max_upscale_factor = parse_float_env(
        "DOCX_AI_RECONSTRUCTION_MAX_UPSCALE_FACTOR",
        reconstruction_max_upscale_factor,
    )
    reconstruction_background_sample_ratio = parse_float_env(
        "DOCX_AI_RECONSTRUCTION_BACKGROUND_SAMPLE_RATIO",
        reconstruction_background_sample_ratio,
    )
    reconstruction_background_color_distance_threshold = parse_float_env(
        "DOCX_AI_RECONSTRUCTION_BACKGROUND_COLOR_DISTANCE_THRESHOLD",
        reconstruction_background_color_distance_threshold,
    )
    reconstruction_background_uniformity_threshold = parse_float_env(
        "DOCX_AI_RECONSTRUCTION_BACKGROUND_UNIFORMITY_THRESHOLD",
        reconstruction_background_uniformity_threshold,
    )

    if default_model not in model_options:
        model_options = [default_model, *[item for item in model_options if item != default_model]]

    return AppConfig(
        default_model=default_model,
        model_options=model_options,
        chunk_size=max(3000, min(chunk_size, 12000)),
        max_retries=max(1, min(max_retries, 5)),
        image_mode_default=image_mode_default,
        semantic_validation_policy=semantic_validation_policy,
        enable_post_redraw_validation=enable_post_redraw_validation,
        validation_model=validation_model,
        min_semantic_match_score=min_semantic_match_score,
        min_text_match_score=min_text_match_score,
        min_structure_match_score=min_structure_match_score,
        validator_confidence_threshold=validator_confidence_threshold,
        allow_accept_with_partial_text_loss=allow_accept_with_partial_text_loss,
        prefer_deterministic_reconstruction=prefer_deterministic_reconstruction,
        reconstruction_model=reconstruction_model,
        enable_vision_image_analysis=enable_vision_image_analysis,
        enable_vision_image_validation=enable_vision_image_validation,
        semantic_redraw_max_attempts=max(1, min(semantic_redraw_max_attempts, 5)),
        semantic_redraw_max_model_calls_per_image=max(1, min(semantic_redraw_max_model_calls_per_image, 20)),
        dense_text_bypass_threshold=max(1, min(dense_text_bypass_threshold, 80)),
        non_latin_text_bypass_threshold=max(1, min(non_latin_text_bypass_threshold, 80)),
        reconstruction_min_canvas_short_side_px=max(256, min(reconstruction_min_canvas_short_side_px, 4096)),
        reconstruction_target_min_font_px=max(10, min(reconstruction_target_min_font_px, 48)),
        reconstruction_max_upscale_factor=max(1.0, min(reconstruction_max_upscale_factor, 6.0)),
        reconstruction_background_sample_ratio=max(0.01, min(reconstruction_background_sample_ratio, 0.2)),
        reconstruction_background_color_distance_threshold=max(5.0, min(reconstruction_background_color_distance_threshold, 255.0)),
        reconstruction_background_uniformity_threshold=max(1.0, min(reconstruction_background_uniformity_threshold, 64.0)),
    )


def load_system_prompt() -> str:
    try:
        prompt_text = SYSTEM_PROMPT_PATH.read_text(encoding="utf-8").strip()
    except FileNotFoundError as exc:
        raise RuntimeError(f"Не найден файл системного промпта: {SYSTEM_PROMPT_PATH}") from exc

    if not prompt_text:
        raise RuntimeError(f"Файл системного промпта пуст: {SYSTEM_PROMPT_PATH}")

    return prompt_text


def get_client() -> "OpenAI":
    load_project_dotenv()
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("Не найден OPENAI_API_KEY. Добавьте его в .env или переменные окружения.")
    client_cls = OpenAI
    if client_cls is None:
        from openai import OpenAI as imported_openai

        client_cls = imported_openai
    return client_cls(api_key=api_key)
