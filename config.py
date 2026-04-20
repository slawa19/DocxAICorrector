import logging
import os
import tomllib
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from threading import Lock
from typing import Any, TYPE_CHECKING

from dotenv import load_dotenv

from constants import (
    CONFIG_PATH,
    DEFAULT_CHUNK_SIZE,
    DEFAULT_MAX_RETRIES,
    ENV_PATH,
    PROMPTS_DIR,
    SYSTEM_PROMPT_PATH,
)
from image_shared import clamp_score
from logger import log_event
from models import (
    IMAGE_MODE_VALUES,
    PARAGRAPH_BOUNDARY_AI_REVIEW_MODE_VALUES,
    PARAGRAPH_BOUNDARY_NORMALIZATION_MODE_VALUES,
    RELATION_NORMALIZATION_KIND_VALUES,
    RELATION_NORMALIZATION_PROFILE_VALUES,
    STRUCTURE_RECOGNITION_MIN_CONFIDENCE_VALUES,
    ImageMode,
)

OpenAI = None
_CLIENT = None
_CLIENT_LOCK = Lock()
_IMAGE_OUTPUT_SIZE_VALUES = {"256x256", "512x512", "1024x1024", "1024x1536", "1536x1024", "1024x1792", "1792x1024"}
PROCESSING_OPERATION_VALUES = ("edit", "translate")
_MIGRATION_DEFAULT_TEXT_MODEL = "gpt-5.4-mini"
_MIGRATION_DEFAULT_TEXT_MODEL_OPTIONS = (
    "gpt-5.4",
    "gpt-5.4-mini",
    "gpt-5-mini",
)
_MIGRATION_DEFAULT_MODEL_ROLES = {
    "structure_recognition": "gpt-5-mini",
    "image_analysis": "gpt-5.4-mini",
    "image_validation": "gpt-5.4-mini",
    "image_reconstruction": "gpt-5.4-mini",
    "image_generation": "gpt-image-1.5",
    "image_edit": "gpt-image-1.5",
    "image_generation_vision": "gpt-5.4-mini",
}
_LEGACY_TOML_MODEL_KEYS = (
    "default_model",
    "model_options",
    "validation_model",
    "reconstruction_model",
)
STRUCTURE_RECOGNITION_MODE_VALUES = ("off", "auto", "always")
_EMITTED_MODEL_REGISTRY_LOG_KEYS: set[str] = set()



@dataclass(frozen=True)
class LanguageOption:
    code: str
    label: str


@dataclass(frozen=True)
class TextModelConfig:
    default: str
    options: tuple[str, ...]


@dataclass(frozen=True)
class ModelRegistry:
    text: TextModelConfig
    structure_recognition: str
    image_analysis: str
    image_validation: str
    image_reconstruction: str
    image_generation: str
    image_edit: str
    image_generation_vision: str


DEFAULT_SUPPORTED_LANGUAGES = (
    LanguageOption(code="ru", label="Русский"),
    LanguageOption(code="en", label="English"),
    LanguageOption(code="de", label="Deutsch"),
    LanguageOption(code="fr", label="Français"),
    LanguageOption(code="es", label="Español"),
    LanguageOption(code="it", label="Italiano"),
    LanguageOption(code="pl", label="Polski"),
    LanguageOption(code="zh", label="中文"),
    LanguageOption(code="ja", label="日本語"),
)

_PROMPT_OPERATION_PATHS = {
    "edit": PROMPTS_DIR / "operation_edit.txt",
    "translate": PROMPTS_DIR / "operation_translate.txt",
}

_PROMPT_EXAMPLE_PATHS = {
    "edit": PROMPTS_DIR / "example_edit.txt",
    "translate": PROMPTS_DIR / "example_translate.txt",
}

if TYPE_CHECKING:
    from openai import OpenAI as OpenAIClient


@dataclass(frozen=True)
class AppConfig(Mapping[str, Any]):
    models: ModelRegistry
    default_model: str
    model_options: list[str]
    chunk_size: int
    max_retries: int
    processing_operation_default: str
    source_language_default: str
    target_language_default: str
    editorial_intensity_default: str
    supported_languages: tuple[LanguageOption, ...]
    enable_paragraph_markers: bool
    paragraph_boundary_normalization_enabled: bool
    paragraph_boundary_normalization_mode: str
    paragraph_boundary_normalization_save_debug_artifacts: bool
    paragraph_boundary_ai_review_enabled: bool
    paragraph_boundary_ai_review_mode: str
    paragraph_boundary_ai_review_candidate_limit: int
    paragraph_boundary_ai_review_timeout_seconds: int
    paragraph_boundary_ai_review_max_tokens_per_candidate: int
    relation_normalization_enabled: bool
    relation_normalization_profile: str
    relation_normalization_enabled_relation_kinds: tuple[str, ...]
    relation_normalization_save_debug_artifacts: bool
    structure_recognition_mode: str
    structure_recognition_enabled: bool
    structure_recognition_model: str
    structure_recognition_max_window_paragraphs: int
    structure_recognition_overlap_paragraphs: int
    structure_recognition_timeout_seconds: int
    structure_recognition_min_confidence: str
    structure_recognition_cache_enabled: bool
    structure_recognition_save_debug_artifacts: bool
    structure_validation_enabled: bool
    structure_validation_min_paragraphs_for_auto_gate: int
    structure_validation_min_explicit_heading_density: float
    structure_validation_max_suspicious_short_body_ratio_without_escalation: float
    structure_validation_max_all_caps_or_centered_body_ratio_without_escalation: float
    structure_validation_toc_like_sequence_min_length: int
    structure_validation_forbid_heading_only_collapse: bool
    structure_validation_save_debug_artifacts: bool
    output_body_font: str | None
    output_heading_font: str | None
    image_mode_default: str
    semantic_validation_policy: str
    keep_all_image_variants: bool
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
    image_output_generate_size_square: str
    image_output_generate_size_landscape: str
    image_output_generate_size_portrait: str
    image_output_generate_candidate_sizes: tuple[str, ...]
    image_output_edit_candidate_sizes: tuple[str, ...]
    image_output_aspect_ratio_threshold: float
    image_output_trim_tolerance: int
    image_output_trim_padding_ratio: float
    image_output_trim_padding_min_px: int
    image_output_trim_max_loss_ratio: float

    def __getitem__(self, key: str) -> object:
        try:
            return getattr(self, key)
        except AttributeError:
            raise KeyError(key)

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


def parse_optional_str_env(name: str) -> str | None:
    raw_value = os.getenv(name, "").strip()
    return raw_value if raw_value else None


def parse_choice_env(name: str, *, default: str, allowed_values: set[str]) -> str:
    raw_value = os.getenv(name, "").strip().lower()
    if not raw_value:
        return default
    if raw_value not in allowed_values:
        raise RuntimeError(f"Некорректное значение в {name}: {raw_value}")
    return raw_value


def parse_supported_languages(
    value: object,
    *,
    source_name: str,
    default: tuple[LanguageOption, ...] = DEFAULT_SUPPORTED_LANGUAGES,
) -> tuple[LanguageOption, ...]:
    if value is None:
        return default
    if not isinstance(value, list) or not value:
        raise RuntimeError(f"Некорректный список языков в {source_name}")

    parsed: list[LanguageOption] = []
    seen_codes: set[str] = set()
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            raise RuntimeError(f"Некорректная запись языка в {source_name}[{index}]")
        code = str(item.get("code", "")).strip().lower()
        label = str(item.get("label", "")).strip()
        if not code or not label:
            raise RuntimeError(f"Некорректная запись языка в {source_name}[{index}]")
        if code in seen_codes:
            raise RuntimeError(f"Дублирующийся код языка в {source_name}: {code}")
        seen_codes.add(code)
        parsed.append(LanguageOption(code=code, label=label))
    return tuple(parsed)


def _validate_text_transform_context(
    *,
    operation: str,
    source_language: str,
    target_language: str,
    supported_language_codes: set[str],
) -> None:
    if operation not in PROCESSING_OPERATION_VALUES:
        raise RuntimeError(f"Некорректный режим текстовой обработки: {operation}")
    if target_language not in supported_language_codes:
        raise RuntimeError(f"Некорректный целевой язык: {target_language}")
    if source_language == "auto":
        if operation != "translate":
            raise RuntimeError("source_language='auto' поддерживается только для режима translate")
        return
    if source_language not in supported_language_codes:
        raise RuntimeError(f"Некорректный язык оригинала: {source_language}")


def parse_optional_config_str(config_data: dict[str, object], field_name: str) -> str | None:
    value = config_data.get(field_name)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise RuntimeError(f"Некорректное поле {field_name} в {CONFIG_PATH}: ожидается непустая строка")
    return value.strip()


def parse_optional_config_section(
    config_data: dict[str, object],
    field_name: str,
    *,
    parent_name: str | None = None,
) -> dict[str, object]:
    value = config_data.get(field_name)
    if value is None:
        return {}
    if not isinstance(value, dict):
        qualified_name = f"{parent_name}.{field_name}" if parent_name else field_name
        raise RuntimeError(f"Некорректное поле {qualified_name} в {CONFIG_PATH}: ожидается таблица")
    return value


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


def parse_image_output_size(value: str, *, source_name: str) -> str:
    normalized = value.strip().lower()
    if normalized not in _IMAGE_OUTPUT_SIZE_VALUES:
        raise RuntimeError(f"Некорректный размер image output в {source_name}: {value}")
    return normalized


def parse_image_output_size_list(value: object, *, source_name: str, default: tuple[str, ...]) -> tuple[str, ...]:
    if value is None:
        return default
    if not isinstance(value, list):
        raise RuntimeError(f"Некорректный список размеров image output в {source_name}")
    normalized = tuple(parse_image_output_size(item, source_name=source_name) for item in value)
    if not normalized:
        raise RuntimeError(f"Пустой список размеров image output в {source_name}")
    return normalized


def parse_string_list(value: object, *, source_name: str, default: tuple[str, ...]) -> tuple[str, ...]:
    if value is None:
        return default
    if not isinstance(value, list):
        raise RuntimeError(f"Некорректный список строк в {source_name}")
    normalized = tuple(item.strip().lower() for item in value if isinstance(item, str) and item.strip())
    if not normalized:
        raise RuntimeError(f"Пустой список строк в {source_name}")
    if len(normalized) != len(value):
        raise RuntimeError(f"Некорректный список строк в {source_name}")
    return normalized


def parse_image_output_size_csv_env(name: str, default: tuple[str, ...]) -> tuple[str, ...]:
    raw_value = os.getenv(name, "").strip()
    if not raw_value:
        return default
    items = [item.strip() for item in raw_value.split(",") if item.strip()]
    if not items:
        raise RuntimeError(f"Переменная {name} задана, но список размеров пуст.")
    return tuple(parse_image_output_size(item, source_name=name) for item in items)


def _coerce_model_name(value: object, *, source_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RuntimeError(f"Некорректное значение модели в {source_name}: ожидается непустая строка")
    return value.strip()


def _parse_model_options_value(value: object, *, source_name: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise RuntimeError(f"Некорректный список моделей в {source_name}")
    parsed = tuple(_coerce_model_name(item, source_name=source_name) for item in value)
    if not parsed:
        raise RuntimeError(f"Пустой список моделей в {source_name}")
    return parsed


def _dedupe_preserving_order(values: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(values))


def _build_text_model_config(default_model: str, options: tuple[str, ...]) -> TextModelConfig:
    unique_options = _dedupe_preserving_order(options)
    if not unique_options:
        raise RuntimeError("Не задан ни один доступный text model в models.text.options")
    if len(unique_options) != len(options):
        raise RuntimeError("models.text.options содержит дублирующиеся значения моделей")
    if default_model not in unique_options:
        unique_options = (default_model, *tuple(item for item in unique_options if item != default_model))
    return TextModelConfig(default=default_model, options=unique_options)


def _resolve_config_value(container: object | None, key: str) -> object | None:
    if container is None:
        return None
    if isinstance(container, Mapping):
        return container.get(key)
    return getattr(container, key, None)


def _resolve_model_registry_value(container: object | None, role_name: str) -> str | None:
    value = _resolve_config_value(container, role_name)
    if isinstance(value, str) and value.strip():
        return value.strip()
    if isinstance(value, Mapping):
        nested_default = value.get("default")
        if isinstance(nested_default, str) and nested_default.strip():
            return nested_default.strip()
    return None


def _resolve_text_model_config_runtime(config_like: object | None) -> TextModelConfig:
    if config_like is None:
        raise RuntimeError("Text model config is not available without resolved application config.")
    if isinstance(config_like, AppConfig):
        return config_like.models.text
    if isinstance(config_like, ModelRegistry):
        return config_like.text

    models_value = _resolve_config_value(config_like, "models")
    text_value = _resolve_config_value(models_value, "text")
    if isinstance(text_value, TextModelConfig):
        return text_value

    text_default = _resolve_model_registry_value(text_value, "default")
    if text_default is None:
        raise RuntimeError("Text default model is not configured in runtime config.")

    text_options_value = _resolve_config_value(text_value, "options")
    if text_options_value is None:
        raise RuntimeError("Text model options are not configured in runtime config.")
    if not isinstance(text_options_value, (list, tuple)):
        raise RuntimeError("Некорректное значение models.text.options в runtime config")
    text_options = tuple(
        str(item).strip()
        for item in text_options_value
        if isinstance(item, str) and str(item).strip()
    )
    if not text_options:
        raise RuntimeError("Text model options are empty in runtime config.")
    return _build_text_model_config(text_default, text_options)


def _resolve_model_role_runtime(config_like: object | None, role_name: str) -> str:
    if config_like is None:
        raise RuntimeError(f"Model role '{role_name}' is not available without resolved application config.")
    if isinstance(config_like, AppConfig):
        return getattr(config_like.models, role_name)
    if isinstance(config_like, ModelRegistry):
        return getattr(config_like, role_name)

    models_value = _resolve_config_value(config_like, "models")
    if isinstance(models_value, ModelRegistry):
        return getattr(models_value, role_name)

    resolved = _resolve_model_registry_value(models_value, role_name)
    if resolved is not None:
        return resolved

    raise RuntimeError(f"Model role '{role_name}' is not configured in runtime config.")


def get_model_registry(config_like: object | None = None) -> ModelRegistry:
    if config_like is None:
        raise RuntimeError("Model registry is not available without resolved application config.")

    if isinstance(config_like, AppConfig):
        return config_like.models
    if isinstance(config_like, ModelRegistry):
        return config_like

    models_value = _resolve_config_value(config_like, "models")
    if isinstance(models_value, ModelRegistry):
        return models_value

    return ModelRegistry(
        text=_resolve_text_model_config_runtime(config_like),
        structure_recognition=_resolve_model_role_runtime(config_like, "structure_recognition"),
        image_analysis=_resolve_model_role_runtime(config_like, "image_analysis"),
        image_validation=_resolve_model_role_runtime(config_like, "image_validation"),
        image_reconstruction=_resolve_model_role_runtime(config_like, "image_reconstruction"),
        image_generation=_resolve_model_role_runtime(config_like, "image_generation"),
        image_edit=_resolve_model_role_runtime(config_like, "image_edit"),
        image_generation_vision=_resolve_model_role_runtime(config_like, "image_generation_vision"),
    )


def get_model_role_value(config_like: object | None, role_name: str) -> str:
    return _resolve_model_role_runtime(config_like, role_name)


def get_text_model_config(config_like: object | None) -> TextModelConfig:
    return _resolve_text_model_config_runtime(config_like)


def get_text_model_default(config_like: object | None) -> str:
    return get_text_model_config(config_like).default


def get_text_model_options(config_like: object | None) -> tuple[str, ...]:
    return get_text_model_config(config_like).options


def _resolve_text_model_options(
    *,
    config_data: dict[str, object],
    models_text_config: dict[str, object],
) -> tuple[tuple[str, ...], str]:
    new_env_options = parse_csv_env("DOCX_AI_MODELS_TEXT_OPTIONS")
    if new_env_options is not None:
        return tuple(new_env_options), "env:canonical:DOCX_AI_MODELS_TEXT_OPTIONS"
    if "options" in models_text_config:
        return _parse_model_options_value(
            models_text_config.get("options"),
            source_name=f"{CONFIG_PATH}: models.text.options",
        ), "toml:canonical:models.text.options"
    legacy_env_options = parse_csv_env("DOCX_AI_MODEL_OPTIONS")
    if legacy_env_options is not None:
        return tuple(legacy_env_options), "env:legacy:DOCX_AI_MODEL_OPTIONS"
    if "model_options" in config_data:
        return _parse_model_options_value(
            config_data.get("model_options"),
            source_name=f"{CONFIG_PATH}: model_options",
        ), "toml:legacy:model_options"
    return _MIGRATION_DEFAULT_TEXT_MODEL_OPTIONS, "default:migration:text.options"


def _resolve_text_default_model(
    *,
    config_data: dict[str, object],
    models_text_config: dict[str, object],
) -> tuple[str, str]:
    new_env_value = os.getenv("DOCX_AI_MODELS_TEXT_DEFAULT", "").strip()
    if new_env_value:
        return new_env_value, "env:canonical:DOCX_AI_MODELS_TEXT_DEFAULT"
    if "default" in models_text_config:
        return _coerce_model_name(
            models_text_config.get("default"),
            source_name=f"{CONFIG_PATH}: models.text.default",
        ), "toml:canonical:models.text.default"
    legacy_env_value = os.getenv("DOCX_AI_DEFAULT_MODEL", "").strip()
    if legacy_env_value:
        return legacy_env_value, "env:legacy:DOCX_AI_DEFAULT_MODEL"
    if "default_model" in config_data:
        return _coerce_model_name(
            config_data.get("default_model"),
            source_name=f"{CONFIG_PATH}: default_model",
        ), "toml:legacy:default_model"
    return _MIGRATION_DEFAULT_TEXT_MODEL, "default:migration:text.default"


def _resolve_model_role_assignment(
    *,
    role_name: str,
    config_path_suffix: str,
    new_env_name: str,
    new_role_config: dict[str, object],
    fallback_value: str,
    legacy_env_name: str | None = None,
    legacy_config_data: dict[str, object] | None = None,
    legacy_config_label: str | None = None,
    legacy_value_key: str | None = None,
) -> tuple[str, str]:
    new_env_value = os.getenv(new_env_name, "").strip()
    if new_env_value:
        return new_env_value, f"env:canonical:{new_env_name}"
    if "default" in new_role_config:
        return _coerce_model_name(
            new_role_config.get("default"),
            source_name=f"{CONFIG_PATH}: {config_path_suffix}.default",
        ), f"toml:canonical:{config_path_suffix}.default"
    if legacy_env_name:
        legacy_env_value = os.getenv(legacy_env_name, "").strip()
        if legacy_env_value:
            return legacy_env_value, f"env:legacy:{legacy_env_name}"
    if legacy_config_data is not None and legacy_value_key is not None:
        if legacy_value_key in legacy_config_data:
            source_name = legacy_config_label or legacy_value_key
            return _coerce_model_name(
                legacy_config_data.get(legacy_value_key),
                source_name=f"{CONFIG_PATH}: {source_name}",
            ), f"toml:legacy:{source_name}"
    return fallback_value, f"default:migration:{role_name}"


def _log_resolved_model_registry(models: ModelRegistry, model_sources: Mapping[str, str]) -> None:
    dedupe_key = repr(
        (
            models,
            tuple(sorted(model_sources.items())),
        )
    )
    if dedupe_key in _EMITTED_MODEL_REGISTRY_LOG_KEYS:
        return
    _EMITTED_MODEL_REGISTRY_LOG_KEYS.add(dedupe_key)
    log_event(
        logging.INFO,
        "model_registry_resolved",
        "Разрешён централизованный registry моделей.",
        resolved_models={
            "text.default": models.text.default,
            "text.options": list(models.text.options),
            "structure_recognition": models.structure_recognition,
            "image_analysis": models.image_analysis,
            "image_validation": models.image_validation,
            "image_reconstruction": models.image_reconstruction,
            "image_generation": models.image_generation,
            "image_edit": models.image_edit,
            "image_generation_vision": models.image_generation_vision,
        },
        model_sources=dict(model_sources),
    )


def _emit_legacy_model_config_warnings(config_data: Mapping[str, object], model_sources: Mapping[str, str]) -> None:
    for legacy_key in _LEGACY_TOML_MODEL_KEYS:
        if legacy_key in config_data:
            dedupe_key = f"legacy-key:{legacy_key}"
            if dedupe_key in _EMITTED_MODEL_REGISTRY_LOG_KEYS:
                continue
            _EMITTED_MODEL_REGISTRY_LOG_KEYS.add(dedupe_key)
            log_event(
                logging.WARNING,
                "legacy_model_config_key_detected",
                "Обнаружен deprecated legacy model key в config.toml; используйте секцию [models.*].",
                legacy_key=legacy_key,
                replacement="models.text" if legacy_key in {"default_model", "model_options"} else f"models.{legacy_key.removesuffix('_model')}",
            )

    structure_recognition_config = config_data.get("structure_recognition")
    if isinstance(structure_recognition_config, Mapping) and "model" in structure_recognition_config:
        dedupe_key = "legacy-key:structure_recognition.model"
        if dedupe_key not in _EMITTED_MODEL_REGISTRY_LOG_KEYS:
            _EMITTED_MODEL_REGISTRY_LOG_KEYS.add(dedupe_key)
            log_event(
                logging.WARNING,
                "legacy_model_config_key_detected",
                "Обнаружен deprecated legacy model key в config.toml; используйте секцию [models.*].",
                legacy_key="structure_recognition.model",
                replacement="models.structure_recognition.default",
            )

    for role_name, source_name in model_sources.items():
        if ":legacy:" not in source_name:
            continue
        dedupe_key = f"legacy-source:{role_name}:{source_name}"
        if dedupe_key in _EMITTED_MODEL_REGISTRY_LOG_KEYS:
            continue
        _EMITTED_MODEL_REGISTRY_LOG_KEYS.add(dedupe_key)
        warning_message = "Использован deprecated legacy model source; перейдите на canonical registry keys."
        if role_name == "image_analysis" and source_name in {
            "env:legacy:DOCX_AI_VALIDATION_MODEL",
            "toml:legacy:validation_model",
        }:
            warning_message = (
                "Использован deprecated legacy validation model source. Во время миграции он переводится в обе роли: "
                "image_analysis и image_validation. Перейдите на models.image_analysis/default и models.image_validation/default."
            )
        log_event(
            logging.WARNING,
            "legacy_model_config_source_used",
            warning_message,
            role_name=role_name,
            source_name=source_name,
        )


def _reject_legacy_manual_review_aliases(config_data: dict[str, object]) -> None:
    if "enable_post_redraw_validation" in config_data:
        raise RuntimeError(
            "Параметр enable_post_redraw_validation больше не поддерживается. "
            "Используйте keep_all_image_variants."
        )
    if os.getenv("DOCX_AI_ENABLE_POST_REDRAW_VALIDATION", "").strip():
        raise RuntimeError(
            "Переменная DOCX_AI_ENABLE_POST_REDRAW_VALIDATION больше не поддерживается. "
            "Используйте DOCX_AI_KEEP_ALL_IMAGE_VARIANTS."
        )


def _resolve_paragraph_boundary_settings(
    *,
    paragraph_boundary_normalization_config: dict[str, object],
    paragraph_boundary_ai_review_config: dict[str, object],
) -> dict[str, Any]:
    paragraph_boundary_normalization_enabled = parse_config_bool(
        paragraph_boundary_normalization_config,
        "enabled",
        True,
    )
    paragraph_boundary_normalization_mode = parse_choice_str(
        paragraph_boundary_normalization_config,
        "mode",
        "high_only",
        set(PARAGRAPH_BOUNDARY_NORMALIZATION_MODE_VALUES),
    )
    paragraph_boundary_normalization_mode = parse_choice_env(
        "DOCX_AI_PARAGRAPH_BOUNDARY_NORMALIZATION_MODE",
        default=paragraph_boundary_normalization_mode,
        allowed_values=set(PARAGRAPH_BOUNDARY_NORMALIZATION_MODE_VALUES),
    )
    paragraph_boundary_normalization_save_debug_artifacts = parse_config_bool(
        paragraph_boundary_normalization_config,
        "save_debug_artifacts",
        True,
    )
    paragraph_boundary_ai_review_enabled = parse_config_bool(
        paragraph_boundary_ai_review_config,
        "enabled",
        False,
    )
    paragraph_boundary_ai_review_mode = parse_choice_str(
        paragraph_boundary_ai_review_config,
        "mode",
        "off",
        set(PARAGRAPH_BOUNDARY_AI_REVIEW_MODE_VALUES),
    )
    paragraph_boundary_ai_review_candidate_limit = parse_config_int(
        paragraph_boundary_ai_review_config,
        "candidate_limit",
        200,
    )
    paragraph_boundary_ai_review_timeout_seconds = parse_config_int(
        paragraph_boundary_ai_review_config,
        "timeout_seconds",
        30,
    )
    paragraph_boundary_ai_review_max_tokens_per_candidate = parse_config_int(
        paragraph_boundary_ai_review_config,
        "max_tokens_per_candidate",
        120,
    )

    paragraph_boundary_ai_review_enabled = parse_bool_env(
        "DOCX_AI_PARAGRAPH_BOUNDARY_AI_REVIEW_ENABLED",
        paragraph_boundary_ai_review_enabled,
    )
    paragraph_boundary_ai_review_mode = parse_choice_env(
        "DOCX_AI_PARAGRAPH_BOUNDARY_AI_REVIEW_MODE",
        default=paragraph_boundary_ai_review_mode,
        allowed_values=set(PARAGRAPH_BOUNDARY_AI_REVIEW_MODE_VALUES),
    )
    paragraph_boundary_ai_review_candidate_limit = parse_int_env(
        "DOCX_AI_PARAGRAPH_BOUNDARY_AI_REVIEW_CANDIDATE_LIMIT",
        paragraph_boundary_ai_review_candidate_limit,
    )
    paragraph_boundary_ai_review_timeout_seconds = parse_int_env(
        "DOCX_AI_PARAGRAPH_BOUNDARY_AI_REVIEW_TIMEOUT_SECONDS",
        paragraph_boundary_ai_review_timeout_seconds,
    )
    paragraph_boundary_ai_review_max_tokens_per_candidate = parse_int_env(
        "DOCX_AI_PARAGRAPH_BOUNDARY_AI_REVIEW_MAX_TOKENS_PER_CANDIDATE",
        paragraph_boundary_ai_review_max_tokens_per_candidate,
    )

    return {
        "paragraph_boundary_normalization_enabled": paragraph_boundary_normalization_enabled,
        "paragraph_boundary_normalization_mode": paragraph_boundary_normalization_mode,
        "paragraph_boundary_normalization_save_debug_artifacts": paragraph_boundary_normalization_save_debug_artifacts,
        "paragraph_boundary_ai_review_enabled": paragraph_boundary_ai_review_enabled,
        "paragraph_boundary_ai_review_mode": paragraph_boundary_ai_review_mode,
        "paragraph_boundary_ai_review_candidate_limit": _clamp_int(
            paragraph_boundary_ai_review_candidate_limit,
            minimum=1,
            maximum=500,
        ),
        "paragraph_boundary_ai_review_timeout_seconds": _clamp_int(
            paragraph_boundary_ai_review_timeout_seconds,
            minimum=1,
            maximum=120,
        ),
        "paragraph_boundary_ai_review_max_tokens_per_candidate": _clamp_int(
            paragraph_boundary_ai_review_max_tokens_per_candidate,
            minimum=32,
            maximum=512,
        ),
    }


def _resolve_relation_normalization_settings(
    *,
    relation_normalization_config: dict[str, object],
) -> dict[str, Any]:
    relation_normalization_enabled = parse_config_bool(
        relation_normalization_config,
        "enabled",
        True,
    )
    relation_normalization_profile = parse_choice_str(
        relation_normalization_config,
        "profile",
        "phase2_default",
        set(RELATION_NORMALIZATION_PROFILE_VALUES),
    )
    relation_normalization_enabled_relation_kinds = parse_string_list(
        relation_normalization_config.get("enabled_relation_kinds"),
        source_name=f"{CONFIG_PATH}: relation_normalization.enabled_relation_kinds",
        default=tuple(RELATION_NORMALIZATION_KIND_VALUES),
    )
    invalid_relation_kinds = sorted(
        set(relation_normalization_enabled_relation_kinds) - set(RELATION_NORMALIZATION_KIND_VALUES)
    )
    if invalid_relation_kinds:
        raise RuntimeError(
            "Некорректные relation normalization kinds в "
            f"{CONFIG_PATH}: {', '.join(invalid_relation_kinds)}"
        )
    relation_normalization_save_debug_artifacts = parse_config_bool(
        relation_normalization_config,
        "save_debug_artifacts",
        True,
    )
    return {
        "relation_normalization_enabled": relation_normalization_enabled,
        "relation_normalization_profile": relation_normalization_profile,
        "relation_normalization_enabled_relation_kinds": relation_normalization_enabled_relation_kinds,
        "relation_normalization_save_debug_artifacts": relation_normalization_save_debug_artifacts,
    }


def _resolve_structure_recognition_settings(
    *,
    structure_recognition_config: dict[str, object],
) -> dict[str, Any]:
    structure_recognition_has_mode = "mode" in structure_recognition_config
    legacy_structure_recognition_enabled = parse_config_bool(
        structure_recognition_config,
        "enabled",
        False,
    )
    if structure_recognition_has_mode:
        structure_recognition_mode = parse_choice_str(
            structure_recognition_config,
            "mode",
            "off",
            set(STRUCTURE_RECOGNITION_MODE_VALUES),
        )
    else:
        structure_recognition_mode = "always" if legacy_structure_recognition_enabled else "off"
    structure_recognition_max_window_paragraphs = parse_config_int(
        structure_recognition_config,
        "max_window_paragraphs",
        1800,
    )
    structure_recognition_overlap_paragraphs = parse_config_int(
        structure_recognition_config,
        "overlap_paragraphs",
        50,
    )
    structure_recognition_timeout_seconds = parse_config_int(
        structure_recognition_config,
        "timeout_seconds",
        60,
    )
    structure_recognition_min_confidence = parse_choice_str(
        structure_recognition_config,
        "min_confidence",
        "medium",
        set(STRUCTURE_RECOGNITION_MIN_CONFIDENCE_VALUES),
    )
    structure_recognition_cache_enabled = parse_config_bool(
        structure_recognition_config,
        "cache_enabled",
        True,
    )
    structure_recognition_save_debug_artifacts = parse_config_bool(
        structure_recognition_config,
        "save_debug_artifacts",
        True,
    )

    raw_structure_recognition_mode_env = os.getenv("DOCX_AI_STRUCTURE_RECOGNITION_MODE", "").strip().lower()
    if raw_structure_recognition_mode_env:
        if raw_structure_recognition_mode_env not in set(STRUCTURE_RECOGNITION_MODE_VALUES):
            raise RuntimeError(
                f"Некорректное значение в DOCX_AI_STRUCTURE_RECOGNITION_MODE: {raw_structure_recognition_mode_env}"
            )
        structure_recognition_mode = raw_structure_recognition_mode_env
    elif not structure_recognition_has_mode:
        legacy_structure_recognition_enabled = parse_bool_env(
            "DOCX_AI_STRUCTURE_RECOGNITION_ENABLED",
            legacy_structure_recognition_enabled,
        )
        structure_recognition_mode = "always" if legacy_structure_recognition_enabled else "off"

    structure_recognition_max_window_paragraphs = parse_int_env(
        "DOCX_AI_STRUCTURE_RECOGNITION_MAX_WINDOW_PARAGRAPHS",
        structure_recognition_max_window_paragraphs,
    )
    structure_recognition_overlap_paragraphs = parse_int_env(
        "DOCX_AI_STRUCTURE_RECOGNITION_OVERLAP_PARAGRAPHS",
        structure_recognition_overlap_paragraphs,
    )
    structure_recognition_timeout_seconds = parse_int_env(
        "DOCX_AI_STRUCTURE_RECOGNITION_TIMEOUT_SECONDS",
        structure_recognition_timeout_seconds,
    )
    structure_recognition_min_confidence = parse_choice_env(
        "DOCX_AI_STRUCTURE_RECOGNITION_MIN_CONFIDENCE",
        default=structure_recognition_min_confidence,
        allowed_values=set(STRUCTURE_RECOGNITION_MIN_CONFIDENCE_VALUES),
    )
    structure_recognition_cache_enabled = parse_bool_env(
        "DOCX_AI_STRUCTURE_RECOGNITION_CACHE_ENABLED",
        structure_recognition_cache_enabled,
    )
    structure_recognition_save_debug_artifacts = parse_bool_env(
        "DOCX_AI_STRUCTURE_RECOGNITION_SAVE_DEBUG_ARTIFACTS",
        structure_recognition_save_debug_artifacts,
    )

    return {
        "structure_recognition_mode": structure_recognition_mode,
        "structure_recognition_enabled": structure_recognition_mode == "always",
        "structure_recognition_max_window_paragraphs": _clamp_int(
            structure_recognition_max_window_paragraphs,
            minimum=100,
            maximum=4000,
        ),
        "structure_recognition_overlap_paragraphs": _clamp_int(
            structure_recognition_overlap_paragraphs,
            minimum=0,
            maximum=200,
        ),
        "structure_recognition_timeout_seconds": _clamp_int(
            structure_recognition_timeout_seconds,
            minimum=1,
            maximum=300,
        ),
        "structure_recognition_min_confidence": structure_recognition_min_confidence,
        "structure_recognition_cache_enabled": structure_recognition_cache_enabled,
        "structure_recognition_save_debug_artifacts": structure_recognition_save_debug_artifacts,
    }


def _resolve_structure_validation_settings(
    *,
    structure_validation_config: dict[str, object],
) -> dict[str, Any]:
    structure_validation_enabled = parse_config_bool(
        structure_validation_config,
        "enabled",
        True,
    )
    structure_validation_min_paragraphs_for_auto_gate = parse_config_int(
        structure_validation_config,
        "min_paragraphs_for_auto_gate",
        40,
    )
    structure_validation_min_explicit_heading_density = parse_config_float(
        structure_validation_config,
        "min_explicit_heading_density",
        0.003,
    )
    structure_validation_max_suspicious_short_body_ratio_without_escalation = parse_config_float(
        structure_validation_config,
        "max_suspicious_short_body_ratio_without_escalation",
        0.05,
    )
    structure_validation_max_all_caps_or_centered_body_ratio_without_escalation = parse_config_float(
        structure_validation_config,
        "max_all_caps_or_centered_body_ratio_without_escalation",
        0.03,
    )
    structure_validation_toc_like_sequence_min_length = parse_config_int(
        structure_validation_config,
        "toc_like_sequence_min_length",
        4,
    )
    structure_validation_forbid_heading_only_collapse = parse_config_bool(
        structure_validation_config,
        "forbid_heading_only_collapse",
        True,
    )
    structure_validation_save_debug_artifacts = parse_config_bool(
        structure_validation_config,
        "save_debug_artifacts",
        True,
    )

    structure_validation_enabled = parse_bool_env(
        "DOCX_AI_STRUCTURE_VALIDATION_ENABLED",
        structure_validation_enabled,
    )
    structure_validation_min_paragraphs_for_auto_gate = parse_int_env(
        "DOCX_AI_STRUCTURE_VALIDATION_MIN_PARAGRAPHS_FOR_AUTO_GATE",
        structure_validation_min_paragraphs_for_auto_gate,
    )
    structure_validation_min_explicit_heading_density = parse_float_env(
        "DOCX_AI_STRUCTURE_VALIDATION_MIN_EXPLICIT_HEADING_DENSITY",
        structure_validation_min_explicit_heading_density,
    )
    structure_validation_max_suspicious_short_body_ratio_without_escalation = parse_float_env(
        "DOCX_AI_STRUCTURE_VALIDATION_MAX_SUSPICIOUS_SHORT_BODY_RATIO_WITHOUT_ESCALATION",
        structure_validation_max_suspicious_short_body_ratio_without_escalation,
    )
    structure_validation_max_all_caps_or_centered_body_ratio_without_escalation = parse_float_env(
        "DOCX_AI_STRUCTURE_VALIDATION_MAX_ALL_CAPS_OR_CENTERED_BODY_RATIO_WITHOUT_ESCALATION",
        structure_validation_max_all_caps_or_centered_body_ratio_without_escalation,
    )
    structure_validation_toc_like_sequence_min_length = parse_int_env(
        "DOCX_AI_STRUCTURE_VALIDATION_TOC_LIKE_SEQUENCE_MIN_LENGTH",
        structure_validation_toc_like_sequence_min_length,
    )
    structure_validation_forbid_heading_only_collapse = parse_bool_env(
        "DOCX_AI_STRUCTURE_VALIDATION_FORBID_HEADING_ONLY_COLLAPSE",
        structure_validation_forbid_heading_only_collapse,
    )
    structure_validation_save_debug_artifacts = parse_bool_env(
        "DOCX_AI_STRUCTURE_VALIDATION_SAVE_DEBUG_ARTIFACTS",
        structure_validation_save_debug_artifacts,
    )

    return {
        "structure_validation_enabled": structure_validation_enabled,
        "structure_validation_min_paragraphs_for_auto_gate": _clamp_int(
            structure_validation_min_paragraphs_for_auto_gate,
            minimum=1,
            maximum=10000,
        ),
        "structure_validation_min_explicit_heading_density": _clamp_float(
            structure_validation_min_explicit_heading_density,
            minimum=0.0,
            maximum=1.0,
        ),
        "structure_validation_max_suspicious_short_body_ratio_without_escalation": _clamp_float(
            structure_validation_max_suspicious_short_body_ratio_without_escalation,
            minimum=0.0,
            maximum=1.0,
        ),
        "structure_validation_max_all_caps_or_centered_body_ratio_without_escalation": _clamp_float(
            structure_validation_max_all_caps_or_centered_body_ratio_without_escalation,
            minimum=0.0,
            maximum=1.0,
        ),
        "structure_validation_toc_like_sequence_min_length": _clamp_int(
            structure_validation_toc_like_sequence_min_length,
            minimum=1,
            maximum=100,
        ),
        "structure_validation_forbid_heading_only_collapse": structure_validation_forbid_heading_only_collapse,
        "structure_validation_save_debug_artifacts": structure_validation_save_debug_artifacts,
    }


def _resolve_semantic_validation_and_runtime_settings(
    *,
    config_data: dict[str, object],
) -> dict[str, Any]:
    image_mode_default = _parse_image_mode(
        parse_config_str(config_data, "image_mode_default", ImageMode.NO_CHANGE.value),
        source_name=str(CONFIG_PATH),
    )
    semantic_validation_policy = parse_choice_str(
        config_data,
        "semantic_validation_policy",
        "advisory",
        {"advisory", "strict"},
    )
    keep_all_image_variants = parse_config_bool(config_data, "keep_all_image_variants", False)
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
        config_data,
        "prefer_deterministic_reconstruction",
        True,
    )
    enable_vision_image_analysis = parse_config_bool(config_data, "enable_vision_image_analysis", True)
    enable_vision_image_validation = parse_config_bool(config_data, "enable_vision_image_validation", True)
    semantic_redraw_max_attempts = parse_config_int(config_data, "semantic_redraw_max_attempts", 2)
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

    image_mode_default = _parse_image_mode(
        os.getenv("DOCX_AI_IMAGE_MODE_DEFAULT", image_mode_default).strip() or image_mode_default,
        source_name="DOCX_AI_IMAGE_MODE_DEFAULT",
    )
    keep_all_image_variants = parse_bool_env(
        "DOCX_AI_KEEP_ALL_IMAGE_VARIANTS",
        keep_all_image_variants,
    )
    semantic_validation_policy = os.getenv(
        "DOCX_AI_SEMANTIC_VALIDATION_POLICY",
        semantic_validation_policy,
    ).strip().lower() or semantic_validation_policy
    if semantic_validation_policy not in {"advisory", "strict"}:
        raise RuntimeError(
            f"Некорректное значение в DOCX_AI_SEMANTIC_VALIDATION_POLICY: {semantic_validation_policy}"
        )
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

    return {
        "image_mode_default": image_mode_default,
        "semantic_validation_policy": semantic_validation_policy,
        "keep_all_image_variants": keep_all_image_variants,
        "min_semantic_match_score": min_semantic_match_score,
        "min_text_match_score": min_text_match_score,
        "min_structure_match_score": min_structure_match_score,
        "validator_confidence_threshold": validator_confidence_threshold,
        "allow_accept_with_partial_text_loss": allow_accept_with_partial_text_loss,
        "prefer_deterministic_reconstruction": prefer_deterministic_reconstruction,
        "enable_vision_image_analysis": enable_vision_image_analysis,
        "enable_vision_image_validation": enable_vision_image_validation,
        "semantic_redraw_max_attempts": _clamp_int(semantic_redraw_max_attempts, minimum=1, maximum=2),
        "semantic_redraw_max_model_calls_per_image": _clamp_int(
            semantic_redraw_max_model_calls_per_image,
            minimum=1,
            maximum=20,
        ),
        "dense_text_bypass_threshold": _clamp_int(dense_text_bypass_threshold, minimum=1, maximum=80),
        "non_latin_text_bypass_threshold": _clamp_int(non_latin_text_bypass_threshold, minimum=1, maximum=80),
        "reconstruction_min_canvas_short_side_px": _clamp_int(
            reconstruction_min_canvas_short_side_px,
            minimum=256,
            maximum=4096,
        ),
        "reconstruction_target_min_font_px": _clamp_int(
            reconstruction_target_min_font_px,
            minimum=10,
            maximum=48,
        ),
        "reconstruction_max_upscale_factor": _clamp_float(
            reconstruction_max_upscale_factor,
            minimum=1.0,
            maximum=6.0,
        ),
        "reconstruction_background_sample_ratio": _clamp_float(
            reconstruction_background_sample_ratio,
            minimum=0.01,
            maximum=0.2,
        ),
        "reconstruction_background_color_distance_threshold": _clamp_float(
            reconstruction_background_color_distance_threshold,
            minimum=5.0,
            maximum=255.0,
        ),
        "reconstruction_background_uniformity_threshold": _clamp_float(
            reconstruction_background_uniformity_threshold,
            minimum=1.0,
            maximum=64.0,
        ),
    }


def _resolve_image_output_settings(
    *,
    image_output_config: dict[str, object],
) -> dict[str, Any]:
    image_output_generate_size_square = parse_image_output_size(
        parse_config_str(image_output_config, "generate_size_square", "1024x1024"),
        source_name=f"{CONFIG_PATH}: image_output.generate_size_square",
    )
    image_output_generate_size_landscape = parse_image_output_size(
        parse_config_str(image_output_config, "generate_size_landscape", "1536x1024"),
        source_name=f"{CONFIG_PATH}: image_output.generate_size_landscape",
    )
    image_output_generate_size_portrait = parse_image_output_size(
        parse_config_str(image_output_config, "generate_size_portrait", "1024x1536"),
        source_name=f"{CONFIG_PATH}: image_output.generate_size_portrait",
    )
    image_output_aspect_ratio_threshold = parse_config_float(
        image_output_config,
        "aspect_ratio_threshold",
        1.2,
    )
    image_output_generate_candidate_sizes = parse_image_output_size_list(
        image_output_config.get("generate_candidate_sizes"),
        source_name=f"{CONFIG_PATH}: image_output.generate_candidate_sizes",
        default=("1536x1024", "1024x1536", "1024x1024"),
    )
    image_output_edit_candidate_sizes = parse_image_output_size_list(
        image_output_config.get("edit_candidate_sizes"),
        source_name=f"{CONFIG_PATH}: image_output.edit_candidate_sizes",
        default=("1536x1024", "1024x1536", "1024x1024", "512x512", "256x256"),
    )
    image_output_trim_tolerance = parse_config_int(image_output_config, "trim_tolerance", 20)
    image_output_trim_padding_ratio = parse_config_float(image_output_config, "trim_padding_ratio", 0.02)
    image_output_trim_padding_min_px = parse_config_int(image_output_config, "trim_padding_min_px", 4)
    image_output_trim_max_loss_ratio = parse_config_float(image_output_config, "trim_max_loss_ratio", 0.15)

    image_output_generate_size_square = parse_image_output_size(
        os.getenv("DOCX_AI_IMAGE_OUTPUT_GENERATE_SIZE_SQUARE", image_output_generate_size_square).strip()
        or image_output_generate_size_square,
        source_name="DOCX_AI_IMAGE_OUTPUT_GENERATE_SIZE_SQUARE",
    )
    image_output_generate_size_landscape = parse_image_output_size(
        os.getenv("DOCX_AI_IMAGE_OUTPUT_GENERATE_SIZE_LANDSCAPE", image_output_generate_size_landscape).strip()
        or image_output_generate_size_landscape,
        source_name="DOCX_AI_IMAGE_OUTPUT_GENERATE_SIZE_LANDSCAPE",
    )
    image_output_generate_size_portrait = parse_image_output_size(
        os.getenv("DOCX_AI_IMAGE_OUTPUT_GENERATE_SIZE_PORTRAIT", image_output_generate_size_portrait).strip()
        or image_output_generate_size_portrait,
        source_name="DOCX_AI_IMAGE_OUTPUT_GENERATE_SIZE_PORTRAIT",
    )
    image_output_generate_candidate_sizes = parse_image_output_size_csv_env(
        "DOCX_AI_IMAGE_OUTPUT_GENERATE_CANDIDATE_SIZES",
        image_output_generate_candidate_sizes,
    )
    image_output_edit_candidate_sizes = parse_image_output_size_csv_env(
        "DOCX_AI_IMAGE_OUTPUT_EDIT_CANDIDATE_SIZES",
        image_output_edit_candidate_sizes,
    )
    image_output_aspect_ratio_threshold = parse_float_env(
        "DOCX_AI_IMAGE_OUTPUT_ASPECT_RATIO_THRESHOLD",
        image_output_aspect_ratio_threshold,
    )
    image_output_trim_tolerance = parse_int_env(
        "DOCX_AI_IMAGE_OUTPUT_TRIM_TOLERANCE",
        image_output_trim_tolerance,
    )
    image_output_trim_padding_ratio = parse_float_env(
        "DOCX_AI_IMAGE_OUTPUT_TRIM_PADDING_RATIO",
        image_output_trim_padding_ratio,
    )
    image_output_trim_padding_min_px = parse_int_env(
        "DOCX_AI_IMAGE_OUTPUT_TRIM_PADDING_MIN_PX",
        image_output_trim_padding_min_px,
    )
    image_output_trim_max_loss_ratio = parse_float_env(
        "DOCX_AI_IMAGE_OUTPUT_TRIM_MAX_LOSS_RATIO",
        image_output_trim_max_loss_ratio,
    )

    return {
        "image_output_generate_size_square": image_output_generate_size_square,
        "image_output_generate_size_landscape": image_output_generate_size_landscape,
        "image_output_generate_size_portrait": image_output_generate_size_portrait,
        "image_output_generate_candidate_sizes": image_output_generate_candidate_sizes,
        "image_output_edit_candidate_sizes": image_output_edit_candidate_sizes,
        "image_output_aspect_ratio_threshold": _clamp_float(
            image_output_aspect_ratio_threshold,
            minimum=1.01,
            maximum=3.0,
        ),
        "image_output_trim_tolerance": _clamp_int(image_output_trim_tolerance, minimum=0, maximum=64),
        "image_output_trim_padding_ratio": _clamp_float(
            image_output_trim_padding_ratio,
            minimum=0.0,
            maximum=0.25,
        ),
        "image_output_trim_padding_min_px": _clamp_int(
            image_output_trim_padding_min_px,
            minimum=0,
            maximum=128,
        ),
        "image_output_trim_max_loss_ratio": _clamp_float(
            image_output_trim_max_loss_ratio,
            minimum=0.0,
            maximum=0.49,
        ),
    }


def _resolve_text_runtime_defaults(
    *,
    config_data: dict[str, object],
) -> dict[str, Any]:
    chunk_size = config_data.get("chunk_size", DEFAULT_CHUNK_SIZE)
    if not isinstance(chunk_size, int):
        raise RuntimeError(f"Некорректное поле chunk_size в {CONFIG_PATH}")

    max_retries = config_data.get("max_retries", DEFAULT_MAX_RETRIES)
    if not isinstance(max_retries, int):
        raise RuntimeError(f"Некорректное поле max_retries в {CONFIG_PATH}")

    supported_languages = parse_supported_languages(
        config_data.get("supported_languages"),
        source_name=f"{CONFIG_PATH}: supported_languages",
    )
    supported_language_codes = {language.code for language in supported_languages}
    processing_operation_default = parse_choice_str(
        config_data,
        "processing_operation_default",
        "edit",
        set(PROCESSING_OPERATION_VALUES),
    )
    source_language_default = parse_config_str(config_data, "source_language_default", "en").strip().lower()
    target_language_default = parse_config_str(config_data, "target_language_default", "ru").strip().lower()
    editorial_intensity_default = parse_config_str(config_data, "editorial_intensity_default", "literary").strip().lower()
    _validate_text_transform_context(
        operation=processing_operation_default,
        source_language=source_language_default,
        target_language=target_language_default,
        supported_language_codes=supported_language_codes,
    )
    enable_paragraph_markers = parse_config_bool(config_data, "enable_paragraph_markers", False)

    chunk_size = parse_int_env("DOCX_AI_CHUNK_SIZE", chunk_size)
    max_retries = parse_int_env("DOCX_AI_MAX_RETRIES", max_retries)
    processing_operation_default = parse_choice_env(
        "DOCX_AI_PROCESSING_OPERATION_DEFAULT",
        default=processing_operation_default,
        allowed_values=set(PROCESSING_OPERATION_VALUES),
    )
    source_language_default = (
        os.getenv("DOCX_AI_SOURCE_LANGUAGE_DEFAULT", source_language_default).strip().lower()
        or source_language_default
    )
    target_language_default = (
        os.getenv("DOCX_AI_TARGET_LANGUAGE_DEFAULT", target_language_default).strip().lower()
        or target_language_default
    )
    editorial_intensity_default = (
        os.getenv("DOCX_AI_EDITORIAL_INTENSITY_DEFAULT", editorial_intensity_default).strip().lower()
        or editorial_intensity_default
    )
    _validate_text_transform_context(
        operation=processing_operation_default,
        source_language=source_language_default,
        target_language=target_language_default,
        supported_language_codes=supported_language_codes,
    )
    enable_paragraph_markers = parse_bool_env(
        "DOCX_AI_ENABLE_PARAGRAPH_MARKERS",
        enable_paragraph_markers,
    )

    return {
        "chunk_size": _clamp_int(chunk_size, minimum=3000, maximum=12000),
        "max_retries": _clamp_int(max_retries, minimum=1, maximum=5),
        "supported_languages": supported_languages,
        "processing_operation_default": processing_operation_default,
        "source_language_default": source_language_default,
        "target_language_default": target_language_default,
        "editorial_intensity_default": editorial_intensity_default,
        "enable_paragraph_markers": enable_paragraph_markers,
    }


def _resolve_output_font_settings(
    *,
    config_data: dict[str, object],
) -> dict[str, Any]:
    output_config = parse_optional_config_section(config_data, "output")
    output_fonts_config = parse_optional_config_section(output_config, "fonts", parent_name="output")
    output_body_font = parse_optional_config_str(output_fonts_config, "body")
    output_heading_font = parse_optional_config_str(output_fonts_config, "heading")

    output_body_font = parse_optional_str_env("DOCX_AI_OUTPUT_BODY_FONT") or output_body_font
    output_heading_font = parse_optional_str_env("DOCX_AI_OUTPUT_HEADING_FONT") or output_heading_font

    return {
        "output_body_font": output_body_font,
        "output_heading_font": output_heading_font,
    }


def _clamp_int(value: int, *, minimum: int, maximum: int) -> int:
    return max(minimum, min(value, maximum))


def _clamp_float(value: float, *, minimum: float, maximum: float) -> float:
    return max(minimum, min(value, maximum))


def _resolve_model_registry_settings(
    *,
    config_data: dict[str, object],
) -> dict[str, Any]:
    models_config = parse_optional_config_section(config_data, "models")
    models_text_config = parse_optional_config_section(models_config, "text", parent_name="models")
    models_structure_recognition_config = parse_optional_config_section(
        models_config,
        "structure_recognition",
        parent_name="models",
    )
    models_image_analysis_config = parse_optional_config_section(models_config, "image_analysis", parent_name="models")
    models_image_validation_config = parse_optional_config_section(models_config, "image_validation", parent_name="models")
    models_image_reconstruction_config = parse_optional_config_section(
        models_config,
        "image_reconstruction",
        parent_name="models",
    )
    models_image_generation_config = parse_optional_config_section(
        models_config,
        "image_generation",
        parent_name="models",
    )
    models_image_edit_config = parse_optional_config_section(models_config, "image_edit", parent_name="models")
    models_image_generation_vision_config = parse_optional_config_section(
        models_config,
        "image_generation_vision",
        parent_name="models",
    )

    model_options, text_options_source = _resolve_text_model_options(
        config_data=config_data,
        models_text_config=models_text_config,
    )
    default_model, text_default_source = _resolve_text_default_model(
        config_data=config_data,
        models_text_config=models_text_config,
    )
    text_model_config = _build_text_model_config(default_model, model_options)

    structure_recognition_config = parse_optional_config_section(
        config_data,
        "structure_recognition",
    )
    structure_recognition_model, structure_recognition_model_source = _resolve_model_role_assignment(
        role_name="structure_recognition",
        config_path_suffix="models.structure_recognition",
        new_env_name="DOCX_AI_MODELS_STRUCTURE_RECOGNITION_DEFAULT",
        new_role_config=models_structure_recognition_config,
        fallback_value=_MIGRATION_DEFAULT_MODEL_ROLES["structure_recognition"],
        legacy_env_name="DOCX_AI_STRUCTURE_RECOGNITION_MODEL",
        legacy_config_data=structure_recognition_config,
        legacy_config_label="structure_recognition.model",
        legacy_value_key="model",
    )
    image_analysis_model, image_analysis_model_source = _resolve_model_role_assignment(
        role_name="image_analysis",
        config_path_suffix="models.image_analysis",
        new_env_name="DOCX_AI_MODELS_IMAGE_ANALYSIS_DEFAULT",
        new_role_config=models_image_analysis_config,
        fallback_value=_MIGRATION_DEFAULT_MODEL_ROLES["image_analysis"],
        legacy_env_name="DOCX_AI_VALIDATION_MODEL",
        legacy_config_data=config_data,
        legacy_config_label="validation_model",
        legacy_value_key="validation_model",
    )
    image_validation_model, image_validation_model_source = _resolve_model_role_assignment(
        role_name="image_validation",
        config_path_suffix="models.image_validation",
        new_env_name="DOCX_AI_MODELS_IMAGE_VALIDATION_DEFAULT",
        new_role_config=models_image_validation_config,
        fallback_value=_MIGRATION_DEFAULT_MODEL_ROLES["image_validation"],
        legacy_env_name="DOCX_AI_VALIDATION_MODEL",
        legacy_config_data=config_data,
        legacy_config_label="validation_model",
        legacy_value_key="validation_model",
    )
    image_reconstruction_model, image_reconstruction_model_source = _resolve_model_role_assignment(
        role_name="image_reconstruction",
        config_path_suffix="models.image_reconstruction",
        new_env_name="DOCX_AI_MODELS_IMAGE_RECONSTRUCTION_DEFAULT",
        new_role_config=models_image_reconstruction_config,
        fallback_value=_MIGRATION_DEFAULT_MODEL_ROLES["image_reconstruction"],
        legacy_env_name="DOCX_AI_RECONSTRUCTION_MODEL",
        legacy_config_data=config_data,
        legacy_config_label="reconstruction_model",
        legacy_value_key="reconstruction_model",
    )
    image_generation_model, image_generation_model_source = _resolve_model_role_assignment(
        role_name="image_generation",
        config_path_suffix="models.image_generation",
        new_env_name="DOCX_AI_MODELS_IMAGE_GENERATION_DEFAULT",
        new_role_config=models_image_generation_config,
        fallback_value=_MIGRATION_DEFAULT_MODEL_ROLES["image_generation"],
    )
    image_edit_model, image_edit_model_source = _resolve_model_role_assignment(
        role_name="image_edit",
        config_path_suffix="models.image_edit",
        new_env_name="DOCX_AI_MODELS_IMAGE_EDIT_DEFAULT",
        new_role_config=models_image_edit_config,
        fallback_value=_MIGRATION_DEFAULT_MODEL_ROLES["image_edit"],
    )
    image_generation_vision_model, image_generation_vision_model_source = _resolve_model_role_assignment(
        role_name="image_generation_vision",
        config_path_suffix="models.image_generation_vision",
        new_env_name="DOCX_AI_MODELS_IMAGE_GENERATION_VISION_DEFAULT",
        new_role_config=models_image_generation_vision_config,
        fallback_value=_MIGRATION_DEFAULT_MODEL_ROLES["image_generation_vision"],
    )

    models = ModelRegistry(
        text=text_model_config,
        structure_recognition=structure_recognition_model,
        image_analysis=image_analysis_model,
        image_validation=image_validation_model,
        image_reconstruction=image_reconstruction_model,
        image_generation=image_generation_model,
        image_edit=image_edit_model,
        image_generation_vision=image_generation_vision_model,
    )
    model_sources = {
        "text.default": text_default_source,
        "text.options": text_options_source,
        "structure_recognition": structure_recognition_model_source,
        "image_analysis": image_analysis_model_source,
        "image_validation": image_validation_model_source,
        "image_reconstruction": image_reconstruction_model_source,
        "image_generation": image_generation_model_source,
        "image_edit": image_edit_model_source,
        "image_generation_vision": image_generation_vision_model_source,
    }
    _emit_legacy_model_config_warnings(config_data, model_sources)

    return {
        "default_model": default_model,
        "models": models,
        "model_sources": model_sources,
        "structure_recognition_config": structure_recognition_config,
    }


def _build_app_config(
    *,
    model_registry_settings: Mapping[str, Any],
    text_runtime_defaults: Mapping[str, Any],
    paragraph_boundary_settings: Mapping[str, Any],
    relation_normalization_settings: Mapping[str, Any],
    structure_recognition_settings: Mapping[str, Any],
    structure_validation_settings: Mapping[str, Any],
    output_font_settings: Mapping[str, Any],
    semantic_validation_runtime_settings: Mapping[str, Any],
    image_output_settings: Mapping[str, Any],
) -> AppConfig:
    models = model_registry_settings["models"]
    paragraph_boundary_ai_review_mode = paragraph_boundary_settings["paragraph_boundary_ai_review_mode"]
    if not paragraph_boundary_settings["paragraph_boundary_ai_review_enabled"]:
        paragraph_boundary_ai_review_mode = "off"

    return AppConfig(
        models=models,
        default_model=model_registry_settings["default_model"],
        model_options=list(models.text.options),
        chunk_size=text_runtime_defaults["chunk_size"],
        max_retries=text_runtime_defaults["max_retries"],
        processing_operation_default=text_runtime_defaults["processing_operation_default"],
        source_language_default=text_runtime_defaults["source_language_default"],
        target_language_default=text_runtime_defaults["target_language_default"],
        editorial_intensity_default=text_runtime_defaults["editorial_intensity_default"],
        supported_languages=text_runtime_defaults["supported_languages"],
        enable_paragraph_markers=text_runtime_defaults["enable_paragraph_markers"],
        paragraph_boundary_normalization_enabled=paragraph_boundary_settings["paragraph_boundary_normalization_enabled"],
        paragraph_boundary_normalization_mode=paragraph_boundary_settings["paragraph_boundary_normalization_mode"],
        paragraph_boundary_normalization_save_debug_artifacts=paragraph_boundary_settings[
            "paragraph_boundary_normalization_save_debug_artifacts"
        ],
        paragraph_boundary_ai_review_enabled=paragraph_boundary_settings["paragraph_boundary_ai_review_enabled"],
        paragraph_boundary_ai_review_mode=paragraph_boundary_ai_review_mode,
        paragraph_boundary_ai_review_candidate_limit=paragraph_boundary_settings[
            "paragraph_boundary_ai_review_candidate_limit"
        ],
        paragraph_boundary_ai_review_timeout_seconds=paragraph_boundary_settings[
            "paragraph_boundary_ai_review_timeout_seconds"
        ],
        paragraph_boundary_ai_review_max_tokens_per_candidate=paragraph_boundary_settings[
            "paragraph_boundary_ai_review_max_tokens_per_candidate"
        ],
        relation_normalization_enabled=relation_normalization_settings["relation_normalization_enabled"],
        relation_normalization_profile=relation_normalization_settings["relation_normalization_profile"],
        relation_normalization_enabled_relation_kinds=relation_normalization_settings[
            "relation_normalization_enabled_relation_kinds"
        ],
        relation_normalization_save_debug_artifacts=relation_normalization_settings[
            "relation_normalization_save_debug_artifacts"
        ],
        structure_recognition_mode=structure_recognition_settings["structure_recognition_mode"],
        structure_recognition_enabled=structure_recognition_settings["structure_recognition_enabled"],
        structure_recognition_model=models.structure_recognition,
        structure_recognition_max_window_paragraphs=structure_recognition_settings[
            "structure_recognition_max_window_paragraphs"
        ],
        structure_recognition_overlap_paragraphs=structure_recognition_settings[
            "structure_recognition_overlap_paragraphs"
        ],
        structure_recognition_timeout_seconds=structure_recognition_settings[
            "structure_recognition_timeout_seconds"
        ],
        structure_recognition_min_confidence=structure_recognition_settings["structure_recognition_min_confidence"],
        structure_recognition_cache_enabled=structure_recognition_settings["structure_recognition_cache_enabled"],
        structure_recognition_save_debug_artifacts=structure_recognition_settings[
            "structure_recognition_save_debug_artifacts"
        ],
        structure_validation_enabled=structure_validation_settings["structure_validation_enabled"],
        structure_validation_min_paragraphs_for_auto_gate=structure_validation_settings[
            "structure_validation_min_paragraphs_for_auto_gate"
        ],
        structure_validation_min_explicit_heading_density=structure_validation_settings[
            "structure_validation_min_explicit_heading_density"
        ],
        structure_validation_max_suspicious_short_body_ratio_without_escalation=structure_validation_settings[
            "structure_validation_max_suspicious_short_body_ratio_without_escalation"
        ],
        structure_validation_max_all_caps_or_centered_body_ratio_without_escalation=structure_validation_settings[
            "structure_validation_max_all_caps_or_centered_body_ratio_without_escalation"
        ],
        structure_validation_toc_like_sequence_min_length=structure_validation_settings[
            "structure_validation_toc_like_sequence_min_length"
        ],
        structure_validation_forbid_heading_only_collapse=structure_validation_settings[
            "structure_validation_forbid_heading_only_collapse"
        ],
        structure_validation_save_debug_artifacts=structure_validation_settings[
            "structure_validation_save_debug_artifacts"
        ],
        output_body_font=output_font_settings["output_body_font"],
        output_heading_font=output_font_settings["output_heading_font"],
        image_mode_default=semantic_validation_runtime_settings["image_mode_default"],
        semantic_validation_policy=semantic_validation_runtime_settings["semantic_validation_policy"],
        keep_all_image_variants=semantic_validation_runtime_settings["keep_all_image_variants"],
        validation_model=models.image_validation,
        min_semantic_match_score=semantic_validation_runtime_settings["min_semantic_match_score"],
        min_text_match_score=semantic_validation_runtime_settings["min_text_match_score"],
        min_structure_match_score=semantic_validation_runtime_settings["min_structure_match_score"],
        validator_confidence_threshold=semantic_validation_runtime_settings["validator_confidence_threshold"],
        allow_accept_with_partial_text_loss=semantic_validation_runtime_settings[
            "allow_accept_with_partial_text_loss"
        ],
        prefer_deterministic_reconstruction=semantic_validation_runtime_settings[
            "prefer_deterministic_reconstruction"
        ],
        reconstruction_model=models.image_reconstruction,
        enable_vision_image_analysis=semantic_validation_runtime_settings["enable_vision_image_analysis"],
        enable_vision_image_validation=semantic_validation_runtime_settings["enable_vision_image_validation"],
        semantic_redraw_max_attempts=semantic_validation_runtime_settings["semantic_redraw_max_attempts"],
        semantic_redraw_max_model_calls_per_image=semantic_validation_runtime_settings[
            "semantic_redraw_max_model_calls_per_image"
        ],
        dense_text_bypass_threshold=semantic_validation_runtime_settings["dense_text_bypass_threshold"],
        non_latin_text_bypass_threshold=semantic_validation_runtime_settings["non_latin_text_bypass_threshold"],
        reconstruction_min_canvas_short_side_px=semantic_validation_runtime_settings[
            "reconstruction_min_canvas_short_side_px"
        ],
        reconstruction_target_min_font_px=semantic_validation_runtime_settings[
            "reconstruction_target_min_font_px"
        ],
        reconstruction_max_upscale_factor=semantic_validation_runtime_settings[
            "reconstruction_max_upscale_factor"
        ],
        reconstruction_background_sample_ratio=semantic_validation_runtime_settings[
            "reconstruction_background_sample_ratio"
        ],
        reconstruction_background_color_distance_threshold=semantic_validation_runtime_settings[
            "reconstruction_background_color_distance_threshold"
        ],
        reconstruction_background_uniformity_threshold=semantic_validation_runtime_settings[
            "reconstruction_background_uniformity_threshold"
        ],
        image_output_generate_size_square=image_output_settings["image_output_generate_size_square"],
        image_output_generate_size_landscape=image_output_settings["image_output_generate_size_landscape"],
        image_output_generate_size_portrait=image_output_settings["image_output_generate_size_portrait"],
        image_output_generate_candidate_sizes=image_output_settings["image_output_generate_candidate_sizes"],
        image_output_edit_candidate_sizes=image_output_settings["image_output_edit_candidate_sizes"],
        image_output_aspect_ratio_threshold=image_output_settings["image_output_aspect_ratio_threshold"],
        image_output_trim_tolerance=image_output_settings["image_output_trim_tolerance"],
        image_output_trim_padding_ratio=image_output_settings["image_output_trim_padding_ratio"],
        image_output_trim_padding_min_px=image_output_settings["image_output_trim_padding_min_px"],
        image_output_trim_max_loss_ratio=image_output_settings["image_output_trim_max_loss_ratio"],
    )


def load_app_config() -> AppConfig:
    load_project_dotenv()
    config_data: dict[str, object] = {}
    if CONFIG_PATH.exists():
        with CONFIG_PATH.open("rb") as file_handle:
            config_data = tomllib.load(file_handle)
    _reject_legacy_manual_review_aliases(config_data)

    model_registry_settings = _resolve_model_registry_settings(
        config_data=config_data,
    )

    text_runtime_defaults = _resolve_text_runtime_defaults(
        config_data=config_data,
    )
    output_font_settings = _resolve_output_font_settings(
        config_data=config_data,
    )
    image_output_config = parse_optional_config_section(config_data, "image_output")
    paragraph_boundary_normalization_config = parse_optional_config_section(
        config_data,
        "paragraph_boundary_normalization",
    )
    relation_normalization_config = parse_optional_config_section(
        config_data,
        "relation_normalization",
    )
    paragraph_boundary_ai_review_config = parse_optional_config_section(
        config_data,
        "paragraph_boundary_ai_review",
    )
    structure_validation_config = parse_optional_config_section(
        config_data,
        "structure_validation",
    )
    paragraph_boundary_settings = _resolve_paragraph_boundary_settings(
        paragraph_boundary_normalization_config=paragraph_boundary_normalization_config,
        paragraph_boundary_ai_review_config=paragraph_boundary_ai_review_config,
    )
    relation_normalization_settings = _resolve_relation_normalization_settings(
        relation_normalization_config=relation_normalization_config,
    )
    structure_recognition_settings = _resolve_structure_recognition_settings(
        structure_recognition_config=model_registry_settings["structure_recognition_config"],
    )
    structure_validation_settings = _resolve_structure_validation_settings(
        structure_validation_config=structure_validation_config,
    )
    semantic_validation_runtime_settings = _resolve_semantic_validation_and_runtime_settings(
        config_data=config_data,
    )
    image_output_settings = _resolve_image_output_settings(
        image_output_config=image_output_config,
    )
    _log_resolved_model_registry(
        model_registry_settings["models"],
        model_registry_settings["model_sources"],
    )

    return _build_app_config(
        model_registry_settings=model_registry_settings,
        text_runtime_defaults=text_runtime_defaults,
        paragraph_boundary_settings=paragraph_boundary_settings,
        relation_normalization_settings=relation_normalization_settings,
        structure_recognition_settings=structure_recognition_settings,
        structure_validation_settings=structure_validation_settings,
        output_font_settings=output_font_settings,
        semantic_validation_runtime_settings=semantic_validation_runtime_settings,
        image_output_settings=image_output_settings,
    )


def _read_prompt_file(path: Path) -> str:
    try:
        prompt_text = path.read_text(encoding="utf-8").strip()
    except FileNotFoundError as exc:
        raise RuntimeError(f"Не найден файл системного промпта: {path}") from exc
    if not prompt_text:
        raise RuntimeError(f"Файл системного промпта пуст: {path}")
    return prompt_text


def _resolve_language_label(language_code: str) -> str:
    normalized = language_code.strip().lower()
    if normalized == "auto":
        return "определи автоматически по тексту"
    for language in DEFAULT_SUPPORTED_LANGUAGES:
        if language.code == normalized:
            return language.label
    return normalized


@lru_cache(maxsize=32)
def load_system_prompt(
    *,
    operation: str = "edit",
    source_language: str = "en",
    target_language: str = "ru",
    editorial_intensity: str = "literary",
) -> str:
    normalized_operation = operation.strip().lower() or "edit"
    normalized_source_language = source_language.strip().lower() or "en"
    normalized_target_language = target_language.strip().lower() or "ru"
    _validate_text_transform_context(
        operation=normalized_operation,
        source_language=normalized_source_language,
        target_language=normalized_target_language,
        supported_language_codes={language.code for language in DEFAULT_SUPPORTED_LANGUAGES},
    )
    operation_instructions = _read_prompt_file(_PROMPT_OPERATION_PATHS[normalized_operation]).format(
        source_language=_resolve_language_label(normalized_source_language),
        target_language=_resolve_language_label(normalized_target_language),
    )
    example_block = _read_prompt_file(_PROMPT_EXAMPLE_PATHS[normalized_operation]).format(
        source_language=_resolve_language_label(normalized_source_language),
        target_language=_resolve_language_label(normalized_target_language),
    )
    prompt_template = _read_prompt_file(SYSTEM_PROMPT_PATH)
    return prompt_template.format(
        source_language=_resolve_language_label(normalized_source_language),
        target_language=_resolve_language_label(normalized_target_language),
        operation_instructions=operation_instructions,
        example_block=example_block,
    )


def get_client() -> "OpenAIClient":
    global _CLIENT
    if _CLIENT is not None:
        return _CLIENT
    with _CLIENT_LOCK:
        if _CLIENT is not None:
            return _CLIENT

        load_project_dotenv()
        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError("Не найден OPENAI_API_KEY. Добавьте его в .env или переменные окружения.")
        global OpenAI
        client_cls = OpenAI
        if client_cls is None:
            from openai import OpenAI as imported_openai

            client_cls = imported_openai
            OpenAI = imported_openai
        _CLIENT = client_cls(api_key=api_key)
        return _CLIENT
