import logging
import os
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from threading import Lock
from typing import Any, TYPE_CHECKING

from dotenv import load_dotenv

from config_loader_layers import (
    build_app_config_payload,
    load_config_data,
    resolve_app_config_sections,
    resolve_optional_section_configs,
)
from config_model_registry import (
    build_text_model_config as _build_text_model_config_impl,
    coerce_model_name as _coerce_model_name_impl,
    emit_legacy_model_config_warnings as _emit_legacy_model_config_warnings_impl,
    get_model_registry as _get_model_registry_impl,
    parse_model_options_value as _parse_model_options_value_impl,
    resolve_model_registry_settings as _resolve_model_registry_settings_impl,
    resolve_model_role_assignment as _resolve_model_role_assignment_impl,
    resolve_model_role_runtime as _resolve_model_role_runtime_impl,
    resolve_text_default_model as _resolve_text_default_model_impl,
    resolve_text_model_config_runtime as _resolve_text_model_config_runtime_impl,
    resolve_text_model_options as _resolve_text_model_options_impl,
    log_resolved_model_registry as _log_resolved_model_registry_impl,
)
from config_runtime_sections import (
    resolve_image_output_settings as _resolve_image_output_settings_impl,
    resolve_output_font_settings as _resolve_output_font_settings_impl,
    resolve_semantic_validation_and_runtime_settings as _resolve_semantic_validation_and_runtime_settings_impl,
    resolve_text_runtime_defaults as _resolve_text_runtime_defaults_impl,
)
from config_structure_sections import (
    resolve_paragraph_boundary_settings as _resolve_paragraph_boundary_settings_impl,
    resolve_relation_normalization_settings as _resolve_relation_normalization_settings_impl,
    resolve_structure_recognition_settings as _resolve_structure_recognition_settings_impl,
    resolve_structure_validation_settings as _resolve_structure_validation_settings_impl,
)
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

_PROMPT_EDITORIAL_INTENSITY_PATHS = {
    "conservative": PROMPTS_DIR / "editorial_intensity_conservative.txt",
    "literary": PROMPTS_DIR / "editorial_intensity_literary.txt",
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
    translation_second_pass_default: bool
    translation_second_pass_model: str
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
    return _coerce_model_name_impl(value, source_name=source_name)


def _parse_model_options_value(value: object, *, source_name: str) -> tuple[str, ...]:
    return _parse_model_options_value_impl(
        value,
        source_name=source_name,
        coerce_model_name_fn=_coerce_model_name,
    )


def _dedupe_preserving_order(values: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(values))


def _build_text_model_config(default_model: str, options: tuple[str, ...]) -> TextModelConfig:
    return _build_text_model_config_impl(
        default_model,
        options,
        text_model_config_factory_fn=TextModelConfig,
        dedupe_preserving_order_fn=_dedupe_preserving_order,
    )


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
    return _resolve_text_model_config_runtime_impl(
        config_like,
        app_config_type=AppConfig,
        model_registry_type=ModelRegistry,
        text_model_config_type=TextModelConfig,
        build_text_model_config_fn=_build_text_model_config,
    )


def _resolve_model_role_runtime(config_like: object | None, role_name: str) -> str:
    return _resolve_model_role_runtime_impl(
        config_like,
        role_name,
        app_config_type=AppConfig,
        model_registry_type=ModelRegistry,
    )


def get_model_registry(config_like: object | None = None) -> ModelRegistry:
    return _get_model_registry_impl(
        config_like,
        app_config_type=AppConfig,
        model_registry_type=ModelRegistry,
        model_registry_factory_fn=ModelRegistry,
        resolve_text_model_config_runtime_fn=_resolve_text_model_config_runtime,
        resolve_model_role_runtime_fn=_resolve_model_role_runtime,
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
    return _resolve_text_model_options_impl(
        config_data=config_data,
        models_text_config=models_text_config,
        parse_csv_env_fn=parse_csv_env,
        parse_model_options_value_fn=_parse_model_options_value,
        config_path=CONFIG_PATH,
        migration_default_text_model_options=_MIGRATION_DEFAULT_TEXT_MODEL_OPTIONS,
    )


def _resolve_text_default_model(
    *,
    config_data: dict[str, object],
    models_text_config: dict[str, object],
) -> tuple[str, str]:
    return _resolve_text_default_model_impl(
        config_data=config_data,
        models_text_config=models_text_config,
        coerce_model_name_fn=_coerce_model_name,
        config_path=CONFIG_PATH,
        migration_default_text_model=_MIGRATION_DEFAULT_TEXT_MODEL,
    )


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
    return _resolve_model_role_assignment_impl(
        role_name=role_name,
        config_path_suffix=config_path_suffix,
        new_env_name=new_env_name,
        new_role_config=new_role_config,
        fallback_value=fallback_value,
        coerce_model_name_fn=_coerce_model_name,
        config_path=CONFIG_PATH,
        legacy_env_name=legacy_env_name,
        legacy_config_data=legacy_config_data,
        legacy_config_label=legacy_config_label,
        legacy_value_key=legacy_value_key,
    )


def _log_resolved_model_registry(models: ModelRegistry, model_sources: Mapping[str, str]) -> None:
    _log_resolved_model_registry_impl(
        models,
        model_sources,
        emitted_model_registry_log_keys=_EMITTED_MODEL_REGISTRY_LOG_KEYS,
        log_event_fn=log_event,
    )


def _emit_legacy_model_config_warnings(config_data: Mapping[str, object], model_sources: Mapping[str, str]) -> None:
    _emit_legacy_model_config_warnings_impl(
        config_data,
        model_sources,
        legacy_toml_model_keys=_LEGACY_TOML_MODEL_KEYS,
        emitted_model_registry_log_keys=_EMITTED_MODEL_REGISTRY_LOG_KEYS,
        log_event_fn=log_event,
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
    return _resolve_paragraph_boundary_settings_impl(
        paragraph_boundary_normalization_config=paragraph_boundary_normalization_config,
        paragraph_boundary_ai_review_config=paragraph_boundary_ai_review_config,
        parse_config_bool_fn=parse_config_bool,
        parse_choice_str_fn=parse_choice_str,
        parse_choice_env_fn=parse_choice_env,
        parse_config_int_fn=parse_config_int,
        parse_bool_env_fn=parse_bool_env,
        parse_int_env_fn=parse_int_env,
        clamp_int_fn=_clamp_int,
        paragraph_boundary_normalization_mode_values=PARAGRAPH_BOUNDARY_NORMALIZATION_MODE_VALUES,
        paragraph_boundary_ai_review_mode_values=PARAGRAPH_BOUNDARY_AI_REVIEW_MODE_VALUES,
    )


def _resolve_relation_normalization_settings(
    *,
    relation_normalization_config: dict[str, object],
) -> dict[str, Any]:
    return _resolve_relation_normalization_settings_impl(
        relation_normalization_config=relation_normalization_config,
        parse_config_bool_fn=parse_config_bool,
        parse_choice_str_fn=parse_choice_str,
        parse_string_list_fn=parse_string_list,
        config_path=CONFIG_PATH,
        relation_normalization_profile_values=RELATION_NORMALIZATION_PROFILE_VALUES,
        relation_normalization_kind_values=RELATION_NORMALIZATION_KIND_VALUES,
    )


def _resolve_structure_recognition_settings(
    *,
    structure_recognition_config: dict[str, object],
) -> dict[str, Any]:
    return _resolve_structure_recognition_settings_impl(
        structure_recognition_config=structure_recognition_config,
        parse_config_bool_fn=parse_config_bool,
        parse_choice_str_fn=parse_choice_str,
        parse_config_int_fn=parse_config_int,
        parse_int_env_fn=parse_int_env,
        parse_bool_env_fn=parse_bool_env,
        parse_choice_env_fn=parse_choice_env,
        clamp_int_fn=_clamp_int,
        structure_recognition_mode_values=STRUCTURE_RECOGNITION_MODE_VALUES,
        structure_recognition_min_confidence_values=STRUCTURE_RECOGNITION_MIN_CONFIDENCE_VALUES,
    )


def _resolve_structure_validation_settings(
    *,
    structure_validation_config: dict[str, object],
) -> dict[str, Any]:
    return _resolve_structure_validation_settings_impl(
        structure_validation_config=structure_validation_config,
        parse_config_bool_fn=parse_config_bool,
        parse_config_int_fn=parse_config_int,
        parse_config_float_fn=parse_config_float,
        parse_bool_env_fn=parse_bool_env,
        parse_int_env_fn=parse_int_env,
        parse_float_env_fn=parse_float_env,
        clamp_int_fn=_clamp_int,
        clamp_float_fn=_clamp_float,
    )


def _resolve_semantic_validation_and_runtime_settings(
    *,
    config_data: dict[str, object],
) -> dict[str, Any]:
    return _resolve_semantic_validation_and_runtime_settings_impl(
        config_data=config_data,
        parse_image_mode_fn=_parse_image_mode,
        parse_config_str_fn=parse_config_str,
        parse_choice_str_fn=parse_choice_str,
        parse_config_bool_fn=parse_config_bool,
        parse_config_score_fn=parse_config_score,
        parse_config_int_fn=parse_config_int,
        parse_config_float_fn=parse_config_float,
        parse_bool_env_fn=parse_bool_env,
        parse_float_env_fn=parse_float_env,
        parse_int_env_fn=parse_int_env,
        clamp_score_fn=clamp_score,
        clamp_int_fn=_clamp_int,
        clamp_float_fn=_clamp_float,
        config_path=CONFIG_PATH,
        image_mode_default_value=ImageMode.NO_CHANGE.value,
    )


def _resolve_image_output_settings(
    *,
    image_output_config: dict[str, object],
) -> dict[str, Any]:
    return _resolve_image_output_settings_impl(
        image_output_config=image_output_config,
        parse_image_output_size_fn=parse_image_output_size,
        parse_config_str_fn=parse_config_str,
        parse_config_float_fn=parse_config_float,
        parse_image_output_size_list_fn=parse_image_output_size_list,
        parse_config_int_fn=parse_config_int,
        parse_image_output_size_csv_env_fn=parse_image_output_size_csv_env,
        parse_float_env_fn=parse_float_env,
        parse_int_env_fn=parse_int_env,
        clamp_int_fn=_clamp_int,
        clamp_float_fn=_clamp_float,
        config_path=CONFIG_PATH,
    )


def _resolve_text_runtime_defaults(
    *,
    config_data: dict[str, object],
) -> dict[str, Any]:
    return _resolve_text_runtime_defaults_impl(
        config_data=config_data,
        default_chunk_size=DEFAULT_CHUNK_SIZE,
        default_max_retries=DEFAULT_MAX_RETRIES,
        config_path=CONFIG_PATH,
        parse_supported_languages_fn=parse_supported_languages,
        parse_choice_str_fn=parse_choice_str,
        parse_config_str_fn=parse_config_str,
        parse_optional_config_str_fn=parse_optional_config_str,
        validate_text_transform_context_fn=_validate_text_transform_context,
        parse_config_bool_fn=parse_config_bool,
        parse_int_env_fn=parse_int_env,
        parse_choice_env_fn=parse_choice_env,
        parse_bool_env_fn=parse_bool_env,
        parse_optional_str_env_fn=parse_optional_str_env,
        clamp_int_fn=_clamp_int,
        processing_operation_values=PROCESSING_OPERATION_VALUES,
    )


def _resolve_output_font_settings(
    *,
    config_data: dict[str, object],
) -> dict[str, Any]:
    return _resolve_output_font_settings_impl(
        config_data=config_data,
        parse_optional_config_section_fn=parse_optional_config_section,
        parse_optional_config_str_fn=parse_optional_config_str,
        parse_optional_str_env_fn=parse_optional_str_env,
    )


def _clamp_int(value: int, *, minimum: int, maximum: int) -> int:
    return max(minimum, min(value, maximum))


def _clamp_float(value: float, *, minimum: float, maximum: float) -> float:
    return max(minimum, min(value, maximum))


def _resolve_model_registry_settings(
    *,
    config_data: dict[str, object],
) -> dict[str, Any]:
    return _resolve_model_registry_settings_impl(
        config_data=config_data,
        parse_optional_config_section_fn=parse_optional_config_section,
        resolve_text_model_options_fn=_resolve_text_model_options,
        resolve_text_default_model_fn=_resolve_text_default_model,
        build_text_model_config_fn=_build_text_model_config,
        resolve_model_role_assignment_fn=_resolve_model_role_assignment,
        emit_legacy_model_config_warnings_fn=_emit_legacy_model_config_warnings,
        model_registry_factory_fn=ModelRegistry,
        config_path=CONFIG_PATH,
        migration_default_model_roles=_MIGRATION_DEFAULT_MODEL_ROLES,
    )


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
    return AppConfig(
        **build_app_config_payload(
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
    )


def load_app_config() -> AppConfig:
    config_data = load_config_data(
        config_path=CONFIG_PATH,
        load_project_dotenv_fn=load_project_dotenv,
        reject_legacy_manual_review_aliases_fn=_reject_legacy_manual_review_aliases,
    )
    optional_sections = resolve_optional_section_configs(
        config_data,
        parse_optional_config_section_fn=parse_optional_config_section,
    )
    resolved_sections = resolve_app_config_sections(
        config_data=config_data,
        optional_sections=optional_sections,
        resolve_model_registry_settings_fn=_resolve_model_registry_settings,
        resolve_text_runtime_defaults_fn=_resolve_text_runtime_defaults,
        resolve_output_font_settings_fn=_resolve_output_font_settings,
        resolve_paragraph_boundary_settings_fn=_resolve_paragraph_boundary_settings,
        resolve_relation_normalization_settings_fn=_resolve_relation_normalization_settings,
        resolve_structure_recognition_settings_fn=_resolve_structure_recognition_settings,
        resolve_structure_validation_settings_fn=_resolve_structure_validation_settings,
        resolve_semantic_validation_and_runtime_settings_fn=_resolve_semantic_validation_and_runtime_settings,
        resolve_image_output_settings_fn=_resolve_image_output_settings,
    )
    _log_resolved_model_registry(
        resolved_sections.model_registry_settings["models"],
        resolved_sections.model_registry_settings["model_sources"],
    )

    return _build_app_config(
        model_registry_settings=resolved_sections.model_registry_settings,
        text_runtime_defaults=resolved_sections.text_runtime_defaults,
        paragraph_boundary_settings=resolved_sections.paragraph_boundary_settings,
        relation_normalization_settings=resolved_sections.relation_normalization_settings,
        structure_recognition_settings=resolved_sections.structure_recognition_settings,
        structure_validation_settings=resolved_sections.structure_validation_settings,
        output_font_settings=resolved_sections.output_font_settings,
        semantic_validation_runtime_settings=resolved_sections.semantic_validation_runtime_settings,
        image_output_settings=resolved_sections.image_output_settings,
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


def _resolve_editorial_intensity(editorial_intensity: str) -> str:
    normalized = editorial_intensity.strip().lower() or "literary"
    if normalized not in _PROMPT_EDITORIAL_INTENSITY_PATHS:
        raise RuntimeError(
            "Некорректная editorial_intensity. Ожидалось одно из значений: "
            f"{', '.join(sorted(_PROMPT_EDITORIAL_INTENSITY_PATHS))}."
        )
    return normalized


@lru_cache(maxsize=32)
def load_system_prompt(
    *,
    operation: str = "edit",
    source_language: str = "en",
    target_language: str = "ru",
    editorial_intensity: str = "literary",
    prompt_variant: str = "default",
) -> str:
    normalized_operation = operation.strip().lower() or "edit"
    normalized_source_language = source_language.strip().lower() or "en"
    normalized_target_language = target_language.strip().lower() or "ru"
    normalized_editorial_intensity = _resolve_editorial_intensity(editorial_intensity)
    normalized_prompt_variant = prompt_variant.strip().lower() or "default"
    _validate_text_transform_context(
        operation=normalized_operation,
        source_language=normalized_source_language,
        target_language=normalized_target_language,
        supported_language_codes={language.code for language in DEFAULT_SUPPORTED_LANGUAGES},
    )
    if normalized_prompt_variant == "default":
        operation_prompt_path = _PROMPT_OPERATION_PATHS[normalized_operation]
        example_prompt_path = _PROMPT_EXAMPLE_PATHS[normalized_operation]
    elif normalized_prompt_variant == "toc_translate":
        if normalized_operation != "translate":
            raise RuntimeError("prompt_variant toc_translate поддерживается только для translate")
        operation_prompt_path = PROMPTS_DIR / "operation_toc_translate.txt"
        example_prompt_path = PROMPTS_DIR / "example_toc_translate.txt"
    elif normalized_prompt_variant == "literary_polish":
        operation_prompt_path = PROMPTS_DIR / "operation_literary_polish.txt"
        example_prompt_path = PROMPTS_DIR / "example_literary_polish.txt"
        normalized_editorial_intensity = "literary"
    else:
        raise RuntimeError(f"Некорректный prompt_variant: {prompt_variant}")

    operation_instructions = _read_prompt_file(operation_prompt_path).format(
        source_language=_resolve_language_label(normalized_source_language),
        target_language=_resolve_language_label(normalized_target_language),
    )
    example_block = _read_prompt_file(example_prompt_path).format(
        source_language=_resolve_language_label(normalized_source_language),
        target_language=_resolve_language_label(normalized_target_language),
    )
    editorial_intensity_instructions = _read_prompt_file(
        _PROMPT_EDITORIAL_INTENSITY_PATHS[normalized_editorial_intensity]
    ).format(
        source_language=_resolve_language_label(normalized_source_language),
        target_language=_resolve_language_label(normalized_target_language),
    )
    prompt_template = _read_prompt_file(SYSTEM_PROMPT_PATH)
    return prompt_template.format(
        source_language=_resolve_language_label(normalized_source_language),
        target_language=_resolve_language_label(normalized_target_language),
        operation_instructions=operation_instructions,
        editorial_intensity_instructions=editorial_intensity_instructions,
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
