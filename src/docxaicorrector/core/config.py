import hashlib
import logging
import os
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from threading import Lock
from typing import Any, TYPE_CHECKING

from dotenv import dotenv_values

from docxaicorrector.core.config_loader_layers import (
    build_app_config_payload,
    load_config_data,
    resolve_app_config_sections,
    resolve_optional_section_configs,
)
from docxaicorrector.core.config_model_registry import (
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
from docxaicorrector.core.config_runtime_sections import (
    resolve_image_output_settings as _resolve_image_output_settings_impl,
    resolve_output_font_settings as _resolve_output_font_settings_impl,
    resolve_semantic_validation_and_runtime_settings as _resolve_semantic_validation_and_runtime_settings_impl,
    resolve_text_runtime_defaults as _resolve_text_runtime_defaults_impl,
)
from docxaicorrector.core.config_structure_sections import (
    resolve_layout_artifact_cleanup_settings as _resolve_layout_artifact_cleanup_settings_impl,
    resolve_paragraph_boundary_settings as _resolve_paragraph_boundary_settings_impl,
    resolve_relation_normalization_settings as _resolve_relation_normalization_settings_impl,
    resolve_structure_validation_settings as _resolve_structure_validation_settings_impl,
)
from docxaicorrector.core.constants import (
    CONFIG_PATH,
    DEFAULT_CHUNK_SIZE,
    DEFAULT_MAX_RETRIES,
    ENV_PATH,
    PROMPTS_DIR,
    SYSTEM_PROMPT_PATH,
)
from docxaicorrector.core.logger import log_event
from docxaicorrector.image.shared import clamp_score
from docxaicorrector.core.models import (
    IMAGE_MODE_VALUES,
    PARAGRAPH_BOUNDARY_AI_REVIEW_MODE_VALUES,
    PARAGRAPH_BOUNDARY_NORMALIZATION_MODE_VALUES,
    RELATION_NORMALIZATION_KIND_VALUES,
    RELATION_NORMALIZATION_PROFILE_VALUES,
    ImageMode,
)
from docxaicorrector.text.translation_domains import build_translation_domain_instructions

OpenAI = None
Anthropic = None
_CLIENT = None
# The exact cache key under which `_CLIENT` was built (including the resolved-secret
# fingerprint). The `_CLIENT` fast-path may only reuse the global when this matches the
# requested key, so a rotated credential never returns the stale default client.
_CLIENT_CACHE_KEY: str | None = None
_CLIENTS_BY_PROVIDER: dict[str, object] = {}
_CLIENT_LOCK = Lock()
_IMAGE_OUTPUT_SIZE_VALUES = {"256x256", "512x512", "1024x1024", "1024x1536", "1536x1024", "1024x1792", "1792x1024"}
PROCESSING_OPERATION_VALUES = ("edit", "translate", "audiobook")
_SUPPORTED_PROVIDER_IDS = ("openai", "openrouter", "anthropic")
_PROVIDER_CAPABILITIES = {
    "openai": frozenset({"responses_text", "responses_vision", "images_generate", "images_edit"}),
    "openrouter": frozenset({"responses_text"}),
    "anthropic": frozenset({"responses_text"}),
}
_MIGRATION_DEFAULT_TEXT_MODEL = "gpt-5.4-mini"
_MIGRATION_DEFAULT_TEXT_MODEL_OPTIONS = (
    "gpt-5.4",
    "gpt-5.4-mini",
    "gpt-5-mini",
)
_MIGRATION_DEFAULT_MODEL_ROLES = {
    "structure_recognition": _MIGRATION_DEFAULT_TEXT_MODEL,
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


@dataclass(frozen=True)
class ProviderConfig:
    name: str
    enabled: bool
    api_key_env: str
    base_url: str | None = None
    referer: str | None = None
    title: str | None = None
    timeout_seconds: float | None = None


@dataclass(frozen=True)
class ProviderRegistry:
    openai: ProviderConfig
    openrouter: ProviderConfig
    anthropic: ProviderConfig = field(
        default_factory=lambda: ProviderConfig(
            name="anthropic",
            enabled=False,
            api_key_env="ANTHROPIC_API_KEY",
        )
    )


@dataclass(frozen=True)
class ResolvedModelSelector:
    raw_selector: str
    canonical_selector: str
    provider: str
    model_id: str


@dataclass(frozen=True)
class ProviderAvailability:
    selector: ResolvedModelSelector
    provider: ProviderConfig
    enabled: bool
    api_key_env: str
    has_api_key: bool
    error_message: str | None


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
    "audiobook": PROMPTS_DIR / "operation_audiobook.txt",
}

_PROMPT_EDITORIAL_INTENSITY_PATHS = {
    "conservative": PROMPTS_DIR / "editorial_intensity_conservative.txt",
    "literary": PROMPTS_DIR / "editorial_intensity_literary.txt",
}

_PROMPT_EXAMPLE_PATHS = {
    "edit": PROMPTS_DIR / "example_edit.txt",
    "translate": PROMPTS_DIR / "example_translate.txt",
    "audiobook": PROMPTS_DIR / "example_audiobook.txt",
}

if TYPE_CHECKING:
    from openai import OpenAI as OpenAIClient
    from anthropic import Anthropic as AnthropicClient


@dataclass(frozen=True)
class AppConfig(Mapping[str, Any]):
    models: ModelRegistry
    providers: ProviderRegistry
    default_model: str
    model_options: list[str]
    chunk_size: int
    max_retries: int
    processing_operation_default: str
    source_language_default: str
    target_language_default: str
    editorial_intensity_default: str
    translation_domain_default: str
    audiobook_postprocess_default: bool
    audiobook_model: str
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
    layout_artifact_cleanup_enabled: bool
    layout_artifact_cleanup_min_repeat_count: int
    layout_artifact_cleanup_max_repeated_text_chars: int
    layout_artifact_cleanup_save_debug_artifacts: bool
    relation_normalization_enabled: bool
    relation_normalization_profile: str
    relation_normalization_enabled_relation_kinds: tuple[str, ...]
    relation_normalization_save_debug_artifacts: bool
    structure_validation_enabled: bool
    structure_validation_min_paragraphs_for_auto_gate: int
    structure_validation_min_explicit_heading_density: float
    structure_validation_max_suspicious_short_body_ratio_without_escalation: float
    structure_validation_max_all_caps_or_centered_body_ratio_without_escalation: float
    structure_validation_toc_like_sequence_min_length: int
    structure_validation_forbid_heading_only_collapse: bool
    structure_validation_save_debug_artifacts: bool
    structure_validation_block_on_high_risk_noop: bool
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
    reader_cleanup_default: bool = False
    reader_cleanup_model: str = ""
    reader_cleanup_chunk_size: int = 8000
    reader_cleanup_overlap_blocks_before: int = 3
    reader_cleanup_overlap_blocks_after: int = 3
    reader_cleanup_global_plan_enabled: bool = False
    reader_cleanup_max_failed_chunk_ratio: float = 1.0

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
    # Precedence: environment > .env > config defaults. A .env value fills a key
    # only when the process environment has NOT already set it to a non-empty
    # value. In hosted/CI deploys, real secrets and selectors (OPENAI_API_KEY,
    # ANTHROPIC_API_KEY, OPENROUTER_API_KEY, DOCX_AI_* model/provider selectors)
    # are injected as env vars and MUST win over a stray checked-in .env. An
    # absent OR empty/whitespace env var is treated as unset, so local dev and an
    # empty placeholder still get populated from .env.
    for key, value in dotenv_values(dotenv_path=ENV_PATH).items():
        if value is None:
            continue
        current = os.environ.get(key)
        if current is None or current.strip() == "":
            os.environ[key] = value


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
        if operation not in {"translate", "audiobook"}:
            raise RuntimeError("source_language='auto' поддерживается только для режимов translate и audiobook")
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
        normalize_model_selector_fn=_normalize_model_selector_for_registry,
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


def _parse_model_selector(selector: str, *, source_name: str) -> ResolvedModelSelector:
    raw_selector = selector.strip()
    if not raw_selector:
        raise RuntimeError("Некорректный селектор модели: ожидается непустая строка.")

    provider = "openai"
    model_id = raw_selector
    if ":" in raw_selector:
        provider_prefix, provider_model_id = raw_selector.split(":", 1)
        provider = provider_prefix.strip().lower()
        model_id = provider_model_id.strip()
        if not provider or not model_id:
            raise RuntimeError("Некорректный селектор модели: expected '<provider>:<model>' or bare OpenAI model.")
        if provider not in _SUPPORTED_PROVIDER_IDS:
            raise RuntimeError(f"Неизвестный provider '{provider}' в {source_name}.")

    if not model_id:
        raise RuntimeError("Некорректный селектор модели: expected '<provider>:<model>' or bare OpenAI model.")

    return ResolvedModelSelector(
        raw_selector=raw_selector,
        canonical_selector=f"{provider}:{model_id}",
        provider=provider,
        model_id=model_id,
    )


def _normalize_model_selector_for_registry(selector: str) -> str:
    return _parse_model_selector(selector, source_name="models.text").canonical_selector


def _coerce_provider_config(value: object, *, provider_name: str) -> ProviderConfig:
    if isinstance(value, ProviderConfig):
        return value
    if value is None and provider_name == "anthropic":
        return ProviderConfig(name="anthropic", enabled=False, api_key_env="ANTHROPIC_API_KEY")
    if not isinstance(value, Mapping):
        raise RuntimeError(f"Некорректная конфигурация provider '{provider_name}'.")

    enabled = value.get("enabled")
    api_key_env = value.get("api_key_env")
    base_url = value.get("base_url")
    referer = value.get("referer")
    title = value.get("title")
    timeout_seconds = value.get("timeout_seconds")
    if not isinstance(enabled, bool):
        raise RuntimeError(f"Некорректная конфигурация provider '{provider_name}'.")
    if not isinstance(api_key_env, str) or not api_key_env.strip():
        raise RuntimeError(f"Некорректная конфигурация provider '{provider_name}'.")
    for field_name, field_value in (("base_url", base_url), ("referer", referer), ("title", title)):
        if field_value is not None and (not isinstance(field_value, str) or not field_value.strip()):
            raise RuntimeError(f"Некорректная конфигурация provider '{provider_name}.{field_name}'.")
    if timeout_seconds is not None and (
        isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, (int, float)) or timeout_seconds <= 0
    ):
        raise RuntimeError(f"Некорректная конфигурация provider '{provider_name}.timeout_seconds'.")

    return ProviderConfig(
        name=provider_name,
        enabled=enabled,
        api_key_env=api_key_env.strip(),
        base_url=base_url.strip() if isinstance(base_url, str) else None,
        referer=referer.strip() if isinstance(referer, str) else None,
        title=title.strip() if isinstance(title, str) else None,
        timeout_seconds=float(timeout_seconds) if isinstance(timeout_seconds, (int, float)) and not isinstance(timeout_seconds, bool) else None,
    )


def get_provider_registry(config_like: object | None = None) -> ProviderRegistry:
    if config_like is None:
        return load_app_config().providers
    if isinstance(config_like, AppConfig):
        return config_like.providers
    if isinstance(config_like, ProviderRegistry):
        return config_like

    providers_value = _resolve_config_value(config_like, "providers")
    if isinstance(providers_value, ProviderRegistry):
        return providers_value
    if not isinstance(providers_value, Mapping):
        raise RuntimeError("Provider registry is not available without resolved application config.")

    return ProviderRegistry(
        openai=_coerce_provider_config(providers_value.get("openai"), provider_name="openai"),
        openrouter=_coerce_provider_config(providers_value.get("openrouter"), provider_name="openrouter"),
        anthropic=_coerce_provider_config(providers_value.get("anthropic"), provider_name="anthropic"),
    )


def get_provider_config(provider_name: str, config_like: object | None = None) -> ProviderConfig:
    normalized_provider_name = provider_name.strip().lower()
    if normalized_provider_name not in _SUPPORTED_PROVIDER_IDS:
        raise RuntimeError(f"Неизвестный provider '{normalized_provider_name}' в provider client factory.")
    return getattr(get_provider_registry(config_like), normalized_provider_name)


def resolve_model_selector(
    selector: str,
    required_capability: str | None = None,
    *,
    config_like: object | None = None,
    source_name: str = "selector",
) -> ResolvedModelSelector:
    resolved_selector = _parse_model_selector(selector, source_name=source_name)
    provider_config = get_provider_config(resolved_selector.provider, config_like)
    if not provider_config.enabled:
        raise RuntimeError(
            f"Provider '{resolved_selector.provider}' отключён, но selector '{resolved_selector.raw_selector}' требует его использования."
        )
    if required_capability is not None and required_capability not in _PROVIDER_CAPABILITIES[resolved_selector.provider]:
        raise RuntimeError(
            f"Provider '{resolved_selector.provider}' не поддерживает role '{source_name}' / capability '{required_capability}'."
        )
    return resolved_selector


def describe_provider_availability(
    selector: str,
    *,
    app_config: AppConfig | Mapping[str, object],
) -> ProviderAvailability:
    resolved_selector = _parse_model_selector(selector, source_name="selector")
    provider_config = get_provider_config(resolved_selector.provider, app_config)
    load_project_dotenv()
    api_key_value = os.getenv(provider_config.api_key_env, "").strip()
    error_message: str | None = None
    if not provider_config.enabled:
        error_message = (
            f"Provider '{provider_config.name}' отключён, но selector '{resolved_selector.raw_selector}' требует его использования."
        )
    elif not api_key_value:
        error_message = f"Для модели '{resolved_selector.raw_selector}' не найден {provider_config.api_key_env}."
    return ProviderAvailability(
        selector=resolved_selector,
        provider=provider_config,
        enabled=provider_config.enabled,
        api_key_env=provider_config.api_key_env,
        has_api_key=bool(api_key_value),
        error_message=error_message,
    )


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
    fallback_source: str | None = None,
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
        fallback_source=fallback_source,
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


def _resolve_layout_artifact_cleanup_settings(
    *,
    layout_artifact_cleanup_config: dict[str, object],
) -> dict[str, Any]:
    return _resolve_layout_artifact_cleanup_settings_impl(
        layout_artifact_cleanup_config=layout_artifact_cleanup_config,
        parse_config_bool_fn=parse_config_bool,
        parse_config_int_fn=parse_config_int,
        parse_bool_env_fn=parse_bool_env,
        parse_int_env_fn=parse_int_env,
        clamp_int_fn=_clamp_int,
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
        parse_optional_str_env_fn=parse_optional_str_env,
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
    model_registry_settings: Mapping[str, Any],
) -> dict[str, Any]:
    return _resolve_text_runtime_defaults_impl(
        config_data=config_data,
        model_registry_settings=model_registry_settings,
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


def _resolve_provider_registry(*, config_data: dict[str, object]) -> ProviderRegistry:
    providers_config = parse_optional_config_section(config_data, "providers")
    unknown_provider_tables = sorted(set(providers_config) - set(_SUPPORTED_PROVIDER_IDS))
    if unknown_provider_tables:
        raise RuntimeError(f"Неизвестные provider tables в {CONFIG_PATH}: {', '.join(unknown_provider_tables)}")

    def _resolve_provider(
        provider_name: str,
        *,
        default_enabled: bool,
        default_api_key_env: str,
        default_base_url: str | None = None,
        default_referer: str | None = None,
        default_title: str | None = None,
        default_timeout_seconds: float | None = None,
    ) -> ProviderConfig:
        section = parse_optional_config_section(providers_config, provider_name, parent_name="providers")
        enabled_value = section.get("enabled", default_enabled)
        if not isinstance(enabled_value, bool):
            raise RuntimeError(f"Некорректное поле providers.{provider_name}.enabled в {CONFIG_PATH}")
        api_key_env_value = section.get("api_key_env", default_api_key_env)
        if not isinstance(api_key_env_value, str) or not api_key_env_value.strip():
            raise RuntimeError(f"Некорректное поле providers.{provider_name}.api_key_env в {CONFIG_PATH}")

        def _optional_field(field_name: str, default_value: str | None) -> str | None:
            field_value = section.get(field_name, default_value)
            if field_value is None:
                return None
            if not isinstance(field_value, str) or not field_value.strip():
                raise RuntimeError(f"Некорректное поле providers.{provider_name}.{field_name} в {CONFIG_PATH}")
            return field_value.strip()

        enabled = parse_bool_env(f"DOCX_AI_PROVIDERS_{provider_name.upper()}_ENABLED", enabled_value)
        base_url = _optional_field("base_url", default_base_url)
        referer = _optional_field("referer", default_referer)
        title = _optional_field("title", default_title)
        timeout_seconds_value = section.get("timeout_seconds", default_timeout_seconds)
        if timeout_seconds_value is not None and (
            isinstance(timeout_seconds_value, bool)
            or not isinstance(timeout_seconds_value, (int, float))
            or timeout_seconds_value <= 0
        ):
            raise RuntimeError(f"Некорректное поле providers.{provider_name}.timeout_seconds в {CONFIG_PATH}")

        if provider_name == "openrouter":
            base_url = parse_optional_str_env("DOCX_AI_PROVIDERS_OPENROUTER_BASE_URL") or base_url
            referer = parse_optional_str_env("DOCX_AI_PROVIDERS_OPENROUTER_REFERER") or referer
            title = parse_optional_str_env("DOCX_AI_PROVIDERS_OPENROUTER_TITLE") or title
        if provider_name == "anthropic":
            env_timeout = parse_optional_str_env("DOCX_AI_PROVIDERS_ANTHROPIC_TIMEOUT_SECONDS")
            if env_timeout:
                try:
                    timeout_seconds_value = float(env_timeout)
                except ValueError as exc:
                    raise RuntimeError(
                        "Некорректное поле DOCX_AI_PROVIDERS_ANTHROPIC_TIMEOUT_SECONDS в environment."
                    ) from exc
                if timeout_seconds_value <= 0:
                    raise RuntimeError("Некорректное поле DOCX_AI_PROVIDERS_ANTHROPIC_TIMEOUT_SECONDS в environment.")

        return ProviderConfig(
            name=provider_name,
            enabled=enabled,
            api_key_env=api_key_env_value.strip(),
            base_url=base_url,
            referer=referer,
            title=title,
            timeout_seconds=(
                float(timeout_seconds_value)
                if isinstance(timeout_seconds_value, (int, float)) and not isinstance(timeout_seconds_value, bool)
                else None
            ),
        )

    return ProviderRegistry(
        openai=_resolve_provider(
            "openai",
            default_enabled=True,
            default_api_key_env="OPENAI_API_KEY",
        ),
        openrouter=_resolve_provider(
            "openrouter",
            default_enabled=False,
            default_api_key_env="OPENROUTER_API_KEY",
            default_base_url="https://openrouter.ai/api/v1",
            default_referer="DocxAICorrector",
            default_title="DocxAICorrector",
        ),
        anthropic=_resolve_provider(
            "anthropic",
            default_enabled=False,
            default_api_key_env="ANTHROPIC_API_KEY",
            default_timeout_seconds=1200.0,
        ),
    )


def _validate_provider_model_contracts(
    *,
    provider_registry: ProviderRegistry,
    model_registry_settings: Mapping[str, Any],
    text_runtime_defaults: Mapping[str, Any],
    paragraph_boundary_settings: Mapping[str, Any],
) -> None:
    models = model_registry_settings["models"]
    text_model_config = models.text

    def ensure_selector_supports_capability(selector: str, *, required_capability: str, source_name: str) -> None:
        resolved_selector = _parse_model_selector(selector, source_name=source_name)
        if required_capability not in _PROVIDER_CAPABILITIES[resolved_selector.provider]:
            raise RuntimeError(
                f"Provider '{resolved_selector.provider}' не поддерживает role '{source_name}' / capability '{required_capability}'."
            )

    def ensure_openai_service_role_available(role_name: str) -> None:
        openai_provider = provider_registry.openai
        if not openai_provider.enabled or not os.getenv(openai_provider.api_key_env, "").strip():
            raise RuntimeError(
                f"OpenAI service role '{role_name}' включён, но provider openai недоступен."
            )

    if paragraph_boundary_settings["paragraph_boundary_ai_review_enabled"]:
        ensure_openai_service_role_available("paragraph_boundary_ai_review")

    resolve_model_selector(
        text_model_config.default,
        required_capability="responses_text",
        config_like=provider_registry,
        source_name="models.text.default",
    )
    for index, option in enumerate(text_model_config.options):
        ensure_selector_supports_capability(
            option,
            required_capability="responses_text",
            source_name=f"models.text.options[{index}]",
        )

    resolve_model_selector(
        text_runtime_defaults["audiobook_model"],
        required_capability="responses_text",
        config_like=provider_registry,
        source_name="models.audiobook.default",
    )

    openai_only_roles = {
        "models.image_analysis.default": (models.image_analysis, "responses_vision"),
        "models.image_validation.default": (models.image_validation, "responses_vision"),
        "models.image_reconstruction.default": (models.image_reconstruction, "responses_vision"),
        "models.image_generation.default": (models.image_generation, "images_generate"),
        "models.image_edit.default": (models.image_edit, "images_edit"),
        "models.image_generation_vision.default": (models.image_generation_vision, "responses_vision"),
    }
    for role_name, (selector, required_capability) in openai_only_roles.items():
        resolved_selector = resolve_model_selector(
            selector,
            required_capability=required_capability,
            config_like=provider_registry,
            source_name=role_name,
        )
        if resolved_selector.provider != "openai":
            raise RuntimeError(
                f"Provider '{resolved_selector.provider}' не поддерживает role '{role_name}' / capability '{required_capability}'."
            )

    resolve_model_selector(
        models.structure_recognition,
        required_capability="responses_text",
        config_like=provider_registry,
        source_name="models.structure_recognition.default",
    )

    if paragraph_boundary_settings["paragraph_boundary_ai_review_enabled"]:
        resolved_selector = resolve_model_selector(
            models.structure_recognition,
            required_capability="responses_text",
            config_like=provider_registry,
            source_name="paragraph_boundary_ai_review",
        )
        if resolved_selector.provider != "openai":
            raise RuntimeError(
                "OpenAI service role 'paragraph_boundary_ai_review' включён, но provider openai недоступен."
            )


def _build_app_config(
    *,
    provider_registry: ProviderRegistry,
    model_registry_settings: Mapping[str, Any],
    text_runtime_defaults: Mapping[str, Any],
    paragraph_boundary_settings: Mapping[str, Any],
    relation_normalization_settings: Mapping[str, Any],
    layout_artifact_cleanup_settings: Mapping[str, Any],
    structure_validation_settings: Mapping[str, Any],
    output_font_settings: Mapping[str, Any],
    semantic_validation_runtime_settings: Mapping[str, Any],
    image_output_settings: Mapping[str, Any],
) -> AppConfig:
    return AppConfig(
        **build_app_config_payload(
            provider_registry=provider_registry,
            model_registry_settings=model_registry_settings,
            text_runtime_defaults=text_runtime_defaults,
            paragraph_boundary_settings=paragraph_boundary_settings,
            layout_artifact_cleanup_settings=layout_artifact_cleanup_settings,
            relation_normalization_settings=relation_normalization_settings,
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
        resolve_layout_artifact_cleanup_settings_fn=_resolve_layout_artifact_cleanup_settings,
        resolve_relation_normalization_settings_fn=_resolve_relation_normalization_settings,
        resolve_structure_validation_settings_fn=_resolve_structure_validation_settings,
        resolve_semantic_validation_and_runtime_settings_fn=_resolve_semantic_validation_and_runtime_settings,
        resolve_image_output_settings_fn=_resolve_image_output_settings,
    )
    _log_resolved_model_registry(
        resolved_sections.model_registry_settings["models"],
        resolved_sections.model_registry_settings["model_sources"],
    )
    provider_registry = _resolve_provider_registry(config_data=config_data)
    _validate_provider_model_contracts(
        provider_registry=provider_registry,
        model_registry_settings=resolved_sections.model_registry_settings,
        text_runtime_defaults=resolved_sections.text_runtime_defaults,
        paragraph_boundary_settings=resolved_sections.paragraph_boundary_settings,
    )

    return _build_app_config(
        provider_registry=provider_registry,
        model_registry_settings=resolved_sections.model_registry_settings,
        text_runtime_defaults=resolved_sections.text_runtime_defaults,
        paragraph_boundary_settings=resolved_sections.paragraph_boundary_settings,
        layout_artifact_cleanup_settings=resolved_sections.layout_artifact_cleanup_settings,
        relation_normalization_settings=resolved_sections.relation_normalization_settings,
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
    translation_domain: str = "general",
    source_text: str = "",
) -> str:
    normalized_operation = operation.strip().lower() or "edit"
    normalized_source_language = source_language.strip().lower() or "en"
    normalized_target_language = target_language.strip().lower() or "ru"
    normalized_editorial_intensity = _resolve_editorial_intensity(editorial_intensity)
    normalized_prompt_variant = prompt_variant.strip().lower() or "default"
    normalized_translation_domain = str(translation_domain or "general").strip().lower() or "general"
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
        translation_domain_instructions=(
            build_translation_domain_instructions(
                translation_domain=normalized_translation_domain,
                source_text=source_text,
            )
            or "Специальные доменные инструкции не заданы."
        ),
        example_block=example_block,
    )


def _get_openai_client_class() -> type["OpenAIClient"]:
    global OpenAI
    client_cls = OpenAI
    if client_cls is None:
        from openai import OpenAI as imported_openai

        client_cls = imported_openai
        OpenAI = imported_openai
    return client_cls


def _get_anthropic_client_class() -> type["AnthropicClient"]:
    global Anthropic
    client_cls = Anthropic
    if client_cls is None:
        try:
            from anthropic import Anthropic as imported_anthropic
        except ImportError as exc:
            raise RuntimeError("Provider 'anthropic' требует пакет anthropic из requirements.txt.") from exc

        client_cls = imported_anthropic
        Anthropic = imported_anthropic
    return client_cls


def _fingerprint_secret_value(secret: str) -> str:
    # F9a: fingerprint an ALREADY-RESOLVED secret VALUE (this never re-reads the
    # environment), so a caller can fold the fingerprint of the exact secret it will use
    # to build the client into that client's cache key — a single read feeds both. The raw
    # secret (and any prefix of it) is NEVER placed in the key, logged, or surfaced in
    # errors — only its sha256 hexdigest. An empty/unset secret maps to a stable sentinel
    # so an unset->set transition also re-keys; the sentinel can never collide with a
    # 64-char hexdigest.
    if not secret:
        return "unset"
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


def _fingerprint_provider_secret(api_key_env: str | None) -> str:
    # F9a: fold a stable, non-reversible fingerprint of the RESOLVED api-key secret into
    # the client cache key. Rotating the credential (same env NAME, new VALUE) must yield
    # a different key -> a fresh client, while an unchanged secret keeps the cached client.
    # A missing env name maps to a stable "noenv" sentinel so an unset->set transition also
    # re-keys. This reads the environment; the F16-TOCTOU build path instead fingerprints
    # the single in-lock secret read via ``_fingerprint_secret_value``.
    if not api_key_env:
        return "noenv"
    load_project_dotenv()
    return _fingerprint_secret_value(os.getenv(api_key_env, "").strip())


def _build_provider_client_cache_key(
    normalized_provider_name: str,
    provider_config: ProviderConfig,
    *,
    secret_fingerprint: str | None = None,
) -> str:
    # F16: the resolved client is shaped by base_url, default headers (referer/title),
    # timeout, and which env var supplies the api key — not the provider name alone.
    # Key the cache on a fingerprint of ALL of those. The api-key ENV NAME (identity)
    # is included; the secret VALUE is never placed in the key — only a hash of it (F9a).
    # When ``secret_fingerprint`` is supplied the caller has ALREADY read the secret (the
    # in-lock build path passes the fingerprint of that same read), so the key describes
    # exactly the secret the client is built from and cannot drift (F16-TOCTOU); otherwise
    # the secret is read from the environment here for an optimistic pre-lock lookup.
    header_items = []
    if provider_config.referer:
        header_items.append(("HTTP-Referer", str(provider_config.referer)))
    if provider_config.title:
        header_items.append(("X-OpenRouter-Title", str(provider_config.title)))
    header_fingerprint = ";".join(f"{name}={value}" for name, value in sorted(header_items))
    timeout_fingerprint = "" if provider_config.timeout_seconds is None else repr(provider_config.timeout_seconds)
    resolved_secret_fingerprint = (
        secret_fingerprint
        if secret_fingerprint is not None
        else _fingerprint_provider_secret(provider_config.api_key_env)
    )
    return "|".join(
        (
            normalized_provider_name,
            str(provider_config.base_url or ""),
            header_fingerprint,
            timeout_fingerprint,
            str(provider_config.api_key_env or ""),
            resolved_secret_fingerprint,
        )
    )


def _default_openai_client_cache_key() -> str | None:
    # The `_CLIENT` fast-path holds the default openai client (built via get_client()
    # with config_like=None). Only reuse it when the requested config resolves to that
    # same default fingerprint, so a config-overriding call does not receive the stale
    # default client.
    try:
        default_openai_config = get_provider_config("openai", None)
    except Exception:
        return None
    return _build_provider_client_cache_key("openai", default_openai_config)


def get_provider_client(provider_name: str, *, config_like: object | None = None) -> object:
    normalized_provider_name = provider_name.strip().lower()
    provider_config = get_provider_config(normalized_provider_name, config_like)
    if not provider_config.enabled:
        raise RuntimeError(
            f"Provider '{normalized_provider_name}' отключён, но selector '{normalized_provider_name}:<runtime>' требует его использования."
        )

    # Optimistic pre-lock key: reads the current secret for a lock-free cache hit. It is
    # NEVER used as the store key — the authoritative key is recomputed inside the lock
    # from the SAME secret read that builds the client, so a rotation during the wait can
    # never store a client under a key describing a different secret (F16-TOCTOU).
    client_cache_key = _build_provider_client_cache_key(normalized_provider_name, provider_config)

    global _CLIENT, _CLIENT_CACHE_KEY
    cached_client = _CLIENTS_BY_PROVIDER.get(client_cache_key)
    if cached_client is not None:
        return cached_client  # type: ignore[return-value]
    if normalized_provider_name == "openai" and _CLIENT is not None and _CLIENT_CACHE_KEY == client_cache_key:
        _CLIENTS_BY_PROVIDER[client_cache_key] = _CLIENT
        return _CLIENT

    with _CLIENT_LOCK:
        cached_client = _CLIENTS_BY_PROVIDER.get(client_cache_key)
        if cached_client is not None:
            return cached_client  # type: ignore[return-value]
        if normalized_provider_name == "openai" and _CLIENT is not None and _CLIENT_CACHE_KEY == client_cache_key:
            _CLIENTS_BY_PROVIDER[client_cache_key] = _CLIENT
            return _CLIENT

        load_project_dotenv()
        api_key = os.getenv(provider_config.api_key_env, "").strip()
        if not api_key:
            raise RuntimeError(f"Для модели '{normalized_provider_name}:<runtime>' не найден {provider_config.api_key_env}.")

        # F16-TOCTOU: derive the authoritative cache key from the fingerprint of THIS
        # exact secret read (not a separate pre-lock read that may have rotated), so the
        # stored key always matches the secret the client is actually built with. Re-check
        # the cache under the authoritative key in case a concurrent builder resolving the
        # same secret already stored its client while we were reading.
        client_cache_key = _build_provider_client_cache_key(
            normalized_provider_name,
            provider_config,
            secret_fingerprint=_fingerprint_secret_value(api_key),
        )
        cached_client = _CLIENTS_BY_PROVIDER.get(client_cache_key)
        if cached_client is not None:
            return cached_client  # type: ignore[return-value]
        if normalized_provider_name == "openai" and _CLIENT is not None and _CLIENT_CACHE_KEY == client_cache_key:
            _CLIENTS_BY_PROVIDER[client_cache_key] = _CLIENT
            return _CLIENT

        client_kwargs: dict[str, Any] = {"api_key": api_key}
        default_headers: dict[str, str] = {}
        if provider_config.base_url:
            client_kwargs["base_url"] = provider_config.base_url
        if provider_config.referer:
            default_headers["HTTP-Referer"] = provider_config.referer
        if provider_config.title:
            default_headers["X-OpenRouter-Title"] = provider_config.title
        if default_headers:
            client_kwargs["default_headers"] = default_headers
        if provider_config.timeout_seconds is not None:
            client_kwargs["timeout"] = provider_config.timeout_seconds

        if normalized_provider_name == "anthropic":
            client = _get_anthropic_client_class()(**client_kwargs)
        else:
            client = _get_openai_client_class()(**client_kwargs)
        _CLIENTS_BY_PROVIDER[client_cache_key] = client
        if normalized_provider_name == "openai" and client_cache_key == _default_openai_client_cache_key():
            _CLIENT = client
            _CLIENT_CACHE_KEY = client_cache_key
        return client


def get_client_for_model_selector(
    selector: str,
    required_capability: str,
    *,
    config_like: object | None = None,
) -> object:
    resolved_selector = resolve_model_selector(
        selector,
        required_capability,
        config_like=config_like,
        source_name="model selector",
    )
    try:
        return get_provider_client(resolved_selector.provider, config_like=config_like)
    except RuntimeError as exc:
        error_text = str(exc)
        runtime_marker = f"{resolved_selector.provider}:<runtime>"
        if runtime_marker in error_text:
            raise RuntimeError(error_text.replace(runtime_marker, resolved_selector.raw_selector)) from exc
        raise


def get_client() -> object:
    return get_provider_client("openai")
