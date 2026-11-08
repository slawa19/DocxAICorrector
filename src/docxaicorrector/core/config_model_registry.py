import logging
import os
from collections.abc import Mapping
from typing import Any


# Spec 062: the six image roles, split into the two choices the UI offers. The vision
# model reads images (analysis, validation, reconstruction scene, generation brief); the
# drawing model produces them (images.generate / images.edit).
IMAGE_VISION_ROLE_NAMES = (
    "image_analysis",
    "image_validation",
    "image_reconstruction",
    "image_generation_vision",
)
IMAGE_DRAW_ROLE_NAMES = ("image_generation", "image_edit")
IMAGE_MODEL_ROLE_NAMES = (
    "image_analysis",
    "image_validation",
    "image_reconstruction",
    "image_generation",
    "image_edit",
    "image_generation_vision",
)
# group id -> (roles, config section under [models], env variable for the default)
IMAGE_MODEL_GROUPS: dict[str, tuple[tuple[str, ...], str, str]] = {
    "vision": (IMAGE_VISION_ROLE_NAMES, "image_vision", "DOCX_AI_IMAGE_VISION_MODEL"),
    "draw": (IMAGE_DRAW_ROLE_NAMES, "image_draw", "DOCX_AI_IMAGE_DRAW_MODEL"),
}
IMAGE_MODEL_GROUP_SOURCE_PREFIX = "group:"


def image_model_group_for_role(role_name: str) -> str:
    for group_id, (roles, _section, _env) in IMAGE_MODEL_GROUPS.items():
        if role_name in roles:
            return group_id
    raise KeyError(role_name)


def resolve_image_model_groups(
    *,
    models_config: Mapping[str, object],
    builtin_groups: Mapping[str, tuple[str, tuple[str, ...]]],
    config_path: Any,
) -> dict[str, dict[str, Any]]:
    """Resolve the default and the offered options of the two image-model choices.

    Returns ``{group_id: {"default", "options", "default_source"}}``. The default is
    ``DOCX_AI_IMAGE_<GROUP>_MODEL`` > ``[models.image_<group>].default`` > built-in; options
    come from ``[models.image_<group>].options`` (or the built-in list) and always contain
    the default, first if it was not listed — the same rule ``[models.text]`` follows.
    """

    resolved: dict[str, dict[str, Any]] = {}
    for group_id, (_roles, section_name, env_name) in IMAGE_MODEL_GROUPS.items():
        builtin_default, builtin_options = builtin_groups[group_id]
        raw_section = models_config.get(section_name)
        section: Mapping[str, object] = raw_section if isinstance(raw_section, Mapping) else {}
        if raw_section is not None and not isinstance(raw_section, Mapping):
            raise RuntimeError(f"Некорректная секция models.{section_name} в {config_path}")
        source_prefix = f"{config_path}: models.{section_name}"
        if "options" in section:
            options = parse_model_options_value(
                section.get("options"),
                source_name=f"{source_prefix}.options",
                coerce_model_name_fn=coerce_model_name,
            )
        else:
            options = tuple(builtin_options)
        has_toml_default = toml_table_has_key(section, "default")
        env_value = os.getenv(env_name, "").strip()
        if env_value:
            default, default_source = env_value, f"env:{env_name}"
        elif has_toml_default:
            default = coerce_model_name(section.get("default"), source_name=f"{source_prefix}.default")
            default_source = f"toml:models.{section_name}.default"
        else:
            default, default_source = builtin_default, f"default:builtin:{section_name}"
        options = dedupe_preserving_order(options)
        if default not in options:
            options = (default, *options)
        resolved[group_id] = {"default": default, "options": options, "default_source": default_source}
    return resolved


def toml_table_has_key(table: Mapping[str, object], key: str) -> bool:
    """Whether a ``config.toml`` table sets ``key`` — asked BEFORE the environment is.

    The model resolvers below let an environment variable outrank the TOML key, and used
    to return on the variable without looking at the table at all. ``ReadTrackingConfigData``
    then saw no read of the key, and spec 066's ``config_key_ignored`` reported a key the
    application does read — ``models.text.default`` / ``models.text.options`` on every run
    whose ``.env`` sets ``DOCX_AI_MODELS_TEXT_*`` (real-document runs of 2026-11-08). A key an
    environment variable outranks is shadowed, not unknown: which source won is reported by
    ``model_registry_resolved`` (``model_sources``), and ``config_key_ignored`` stays for keys
    no resolver asks for. Only presence is checked here, so a shadowed value is still not
    parsed or validated, exactly as before.
    """

    return key in table


def coerce_model_name(value: object, *, source_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RuntimeError(f"Некорректное значение модели в {source_name}: ожидается непустая строка")
    return value.strip()


def parse_model_options_value(value: object, *, source_name: str, coerce_model_name_fn: Any) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise RuntimeError(f"Некорректный список моделей в {source_name}")
    parsed = tuple(coerce_model_name_fn(item, source_name=source_name) for item in value)
    if not parsed:
        raise RuntimeError(f"Пустой список моделей в {source_name}")
    return parsed


def dedupe_preserving_order(values: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(values))


def build_text_model_config(
    default_model: str,
    options: tuple[str, ...],
    *,
    text_model_config_factory_fn: Any,
    dedupe_preserving_order_fn: Any,
    normalize_model_selector_fn: Any | None = None,
) -> Any:
    unique_options = dedupe_preserving_order_fn(options)
    if not unique_options:
        raise RuntimeError("Не задан ни один доступный text model в models.text.options")
    if len(unique_options) != len(options):
        raise RuntimeError("models.text.options содержит дублирующиеся значения моделей")

    if normalize_model_selector_fn is not None:
        normalized_options = tuple(normalize_model_selector_fn(item) for item in unique_options)
        if len(set(normalized_options)) != len(normalized_options):
            raise RuntimeError("models.text.options содержит duplicate normalized selectors.")
        default_normalized = normalize_model_selector_fn(default_model)
        if default_normalized not in normalized_options:
            unique_options = (default_model, *tuple(item for item in unique_options if item != default_model))
        return text_model_config_factory_fn(default=default_model, options=unique_options)

    if default_model not in unique_options:
        unique_options = (default_model, *tuple(item for item in unique_options if item != default_model))
    return text_model_config_factory_fn(default=default_model, options=unique_options)


def resolve_config_value(container: object | None, key: str) -> object | None:
    if container is None:
        return None
    if isinstance(container, Mapping):
        return container.get(key)
    return getattr(container, key, None)


def resolve_model_registry_value(container: object | None, role_name: str) -> str | None:
    value = resolve_config_value(container, role_name)
    if isinstance(value, str) and value.strip():
        return value.strip()
    if isinstance(value, Mapping):
        nested_default = value.get("default")
        if isinstance(nested_default, str) and nested_default.strip():
            return nested_default.strip()
    return None


def resolve_text_model_config_runtime(
    config_like: object | None,
    *,
    app_config_type: type,
    model_registry_type: type,
    text_model_config_type: type,
    build_text_model_config_fn: Any,
) -> Any:
    if config_like is None:
        raise RuntimeError("Text model config is not available without resolved application config.")
    if isinstance(config_like, app_config_type):
        models_value = resolve_config_value(config_like, "models")
        text_value = resolve_config_value(models_value, "text")
        if text_value is not None:
            return text_value
    if isinstance(config_like, model_registry_type):
        text_value = resolve_config_value(config_like, "text")
        if text_value is not None:
            return text_value

    models_value = resolve_config_value(config_like, "models")
    text_value = resolve_config_value(models_value, "text")
    if isinstance(text_value, text_model_config_type):
        return text_value

    text_default = resolve_model_registry_value(text_value, "default")
    if text_default is None:
        raise RuntimeError("Text default model is not configured in runtime config.")

    text_options_value = resolve_config_value(text_value, "options")
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
    return build_text_model_config_fn(text_default, text_options)


def resolve_model_role_runtime(
    config_like: object | None,
    role_name: str,
    *,
    app_config_type: type,
    model_registry_type: type,
) -> str:
    if config_like is None:
        raise RuntimeError(f"Model role '{role_name}' is not available without resolved application config.")
    if isinstance(config_like, app_config_type):
        models_value = resolve_config_value(config_like, "models")
        resolved = resolve_model_registry_value(models_value, role_name)
        if resolved is not None:
            return resolved
    if isinstance(config_like, model_registry_type):
        resolved = resolve_model_registry_value(config_like, role_name)
        if resolved is not None:
            return resolved

    models_value = resolve_config_value(config_like, "models")
    if isinstance(models_value, model_registry_type):
        return getattr(models_value, role_name)

    resolved = resolve_model_registry_value(models_value, role_name)
    if resolved is not None:
        return resolved

    raise RuntimeError(f"Model role '{role_name}' is not configured in runtime config.")


def get_model_registry(
    config_like: object | None,
    *,
    app_config_type: type,
    model_registry_type: type,
    model_registry_factory_fn: Any,
    resolve_text_model_config_runtime_fn: Any,
    resolve_model_role_runtime_fn: Any,
) -> Any:
    if config_like is None:
        raise RuntimeError("Model registry is not available without resolved application config.")

    if isinstance(config_like, app_config_type):
        models_value = resolve_config_value(config_like, "models")
        if models_value is not None:
            return models_value
    if isinstance(config_like, model_registry_type):
        return config_like

    models_value = resolve_config_value(config_like, "models")
    if isinstance(models_value, model_registry_type):
        return models_value

    return model_registry_factory_fn(
        text=resolve_text_model_config_runtime_fn(config_like),
        boundary_review=resolve_model_role_runtime_fn(config_like, "boundary_review"),
        image_analysis=resolve_model_role_runtime_fn(config_like, "image_analysis"),
        image_validation=resolve_model_role_runtime_fn(config_like, "image_validation"),
        image_reconstruction=resolve_model_role_runtime_fn(config_like, "image_reconstruction"),
        image_generation=resolve_model_role_runtime_fn(config_like, "image_generation"),
        image_edit=resolve_model_role_runtime_fn(config_like, "image_edit"),
        image_generation_vision=resolve_model_role_runtime_fn(config_like, "image_generation_vision"),
    )


def resolve_text_model_options(
    *,
    models_text_config: dict[str, object],
    parse_csv_env_fn: Any,
    parse_model_options_value_fn: Any,
    config_path: Any,
    migration_default_text_model_options: tuple[str, ...],
) -> tuple[tuple[str, ...], str]:
    has_toml_options = toml_table_has_key(models_text_config, "options")
    new_env_options = parse_csv_env_fn("DOCX_AI_MODELS_TEXT_OPTIONS")
    if new_env_options is not None:
        return tuple(new_env_options), "env:canonical:DOCX_AI_MODELS_TEXT_OPTIONS"
    if has_toml_options:
        return parse_model_options_value_fn(
            models_text_config.get("options"),
            source_name=f"{config_path}: models.text.options",
        ), "toml:canonical:models.text.options"
    # Legacy sources DOCX_AI_MODEL_OPTIONS / top-level model_options are no longer read.
    return migration_default_text_model_options, "default:migration:text.options"


def resolve_text_default_model(
    *,
    models_text_config: dict[str, object],
    coerce_model_name_fn: Any,
    config_path: Any,
    migration_default_text_model: str,
) -> tuple[str, str]:
    has_toml_default = toml_table_has_key(models_text_config, "default")
    new_env_value = os.getenv("DOCX_AI_MODELS_TEXT_DEFAULT", "").strip()
    if new_env_value:
        return new_env_value, "env:canonical:DOCX_AI_MODELS_TEXT_DEFAULT"
    if has_toml_default:
        return coerce_model_name_fn(
            models_text_config.get("default"),
            source_name=f"{config_path}: models.text.default",
        ), "toml:canonical:models.text.default"
    # Legacy sources DOCX_AI_DEFAULT_MODEL / top-level default_model are no longer read.
    return migration_default_text_model, "default:migration:text.default"


def resolve_model_role_assignment(
    *,
    role_name: str,
    config_path_suffix: str,
    new_env_name: str,
    new_role_config: dict[str, object],
    fallback_value: str,
    coerce_model_name_fn: Any,
    config_path: Any,
    fallback_source: str | None = None,
) -> tuple[str, str]:
    has_toml_default = toml_table_has_key(new_role_config, "default")
    new_env_value = os.getenv(new_env_name, "").strip()
    if new_env_value:
        return new_env_value, f"env:canonical:{new_env_name}"
    if has_toml_default:
        return coerce_model_name_fn(
            new_role_config.get("default"),
            source_name=f"{config_path}: {config_path_suffix}.default",
        ), f"toml:canonical:{config_path_suffix}.default"
    return fallback_value, fallback_source or f"default:migration:{role_name}"


def log_resolved_model_registry(
    models: Any,
    model_sources: Mapping[str, str],
    *,
    emitted_model_registry_log_keys: set[str],
    log_event_fn: Any,
    supported_provider_ids: tuple[str, ...],
) -> None:
    # Mirror the real selector parser (core/config.py::_parse_model_selector): every
    # provider it accepts must round-trip unchanged here, otherwise the diagnostic
    # event reports a selector the runtime never uses (e.g. "openai:anthropic:...").
    normalized_supported_providers = {item.strip().lower() for item in supported_provider_ids}

    def _canonicalize_selector(value: str) -> str:
        stripped_value = str(value).strip()
        if ":" in stripped_value:
            provider_name, _, model_id = stripped_value.partition(":")
            normalized_provider = provider_name.strip().lower()
            if normalized_provider in normalized_supported_providers and model_id.strip():
                return f"{normalized_provider}:{model_id.strip()}"
        return f"openai:{stripped_value}"

    dedupe_key = repr((models, tuple(sorted(model_sources.items()))))
    if dedupe_key in emitted_model_registry_log_keys:
        return
    emitted_model_registry_log_keys.add(dedupe_key)
    log_event_fn(
        logging.INFO,
        "model_registry_resolved",
        "Разрешён централизованный registry моделей.",
        resolved_models={
            "text.default": models.text.default,
            "text.options": list(models.text.options),
            "text.canonical_default": _canonicalize_selector(models.text.default),
            "text.canonical_options": [_canonicalize_selector(item) for item in models.text.options],
            "boundary_review": models.boundary_review,
            "image_analysis": models.image_analysis,
            "image_validation": models.image_validation,
            "image_reconstruction": models.image_reconstruction,
            "image_generation": models.image_generation,
            "image_edit": models.image_edit,
            "image_generation_vision": models.image_generation_vision,
        },
        model_sources=dict(model_sources),
    )


def emit_legacy_model_config_warnings(
    config_data: Mapping[str, object],
    model_sources: Mapping[str, str],
    *,
    legacy_toml_model_keys: Mapping[str, str],
    legacy_env_model_keys: Mapping[str, str],
    emitted_model_registry_log_keys: set[str],
    log_event_fn: Any,
) -> None:
    # ``legacy_*_model_keys`` map a removed key onto its canonical replacement. The
    # replacement is spelled out per key instead of derived from the key name: role
    # sections are named ``models.image_validation`` / ``models.image_reconstruction``,
    # which a naive ``removesuffix("_model")`` would render as non-existent
    # ``models.validation`` / ``models.reconstruction`` hints.
    for legacy_key, replacement in legacy_toml_model_keys.items():
        if legacy_key in config_data:
            dedupe_key = f"legacy-key:{legacy_key}"
            if dedupe_key in emitted_model_registry_log_keys:
                continue
            emitted_model_registry_log_keys.add(dedupe_key)
            log_event_fn(
                logging.WARNING,
                "legacy_model_config_key_detected",
                "Обнаружен legacy model key в config.toml; он больше не читается — используйте секцию [models.*].",
                legacy_key=legacy_key,
                replacement=replacement,
            )

    # Removed legacy ENV aliases are no longer read by any resolver. Without this scan
    # an operator whose .env still pins DOCX_AI_DEFAULT_MODEL silently runs on a
    # different model (different price/quality) with no diagnostic line at all.
    for legacy_env_name, replacement_env_name in legacy_env_model_keys.items():
        if not os.getenv(legacy_env_name, "").strip():
            continue
        dedupe_key = f"legacy-env:{legacy_env_name}"
        if dedupe_key in emitted_model_registry_log_keys:
            continue
        emitted_model_registry_log_keys.add(dedupe_key)
        log_event_fn(
            logging.WARNING,
            "legacy_model_config_key_detected",
            "Обнаружена legacy model env-переменная; она больше не читается — используйте canonical DOCX_AI_MODELS_* переменную.",
            legacy_key=legacy_env_name,
            replacement=replacement_env_name,
        )



def resolve_model_registry_settings(
    *,
    config_data: dict[str, object],
    parse_optional_config_section_fn: Any,
    resolve_text_model_options_fn: Any,
    resolve_text_default_model_fn: Any,
    build_text_model_config_fn: Any,
    resolve_model_role_assignment_fn: Any,
    emit_legacy_model_config_warnings_fn: Any,
    model_registry_factory_fn: Any,
    config_path: Any,
    migration_default_model_roles: Mapping[str, str],
    builtin_image_model_groups: Mapping[str, tuple[str, tuple[str, ...]]] | None = None,
) -> dict[str, Any]:
    models_config = parse_optional_config_section_fn(config_data, "models")
    models_text_config = parse_optional_config_section_fn(models_config, "text", parent_name="models")
    models_boundary_review_config = parse_optional_config_section_fn(models_config, "boundary_review", parent_name="models")

    model_options, text_options_source = resolve_text_model_options_fn(
        models_text_config=models_text_config,
    )
    default_model, text_default_source = resolve_text_default_model_fn(
        models_text_config=models_text_config,
    )
    text_model_config = build_text_model_config_fn(default_model, model_options)

    # Spec 066 C-9: the model role of paragraph_boundary_ai_review; it inherits
    # [models.text].default when not set.
    boundary_review_model, boundary_review_model_source = resolve_model_role_assignment_fn(
        role_name="boundary_review",
        config_path_suffix="models.boundary_review",
        new_env_name="DOCX_AI_MODELS_BOUNDARY_REVIEW_DEFAULT",
        new_role_config=models_boundary_review_config,
        fallback_value=default_model,
        fallback_source="default:derived:text.default",
    )
    # Spec 062: each image role resolves per-role override > its group's model. The
    # per-role env and [models.image_<role>] are read exactly as before; only the fallback
    # changed from a fixed migration id to the default of the role's group (vision/draw).
    resolved_builtin_groups = builtin_image_model_groups or {
        "vision": (migration_default_model_roles["image_analysis"], (migration_default_model_roles["image_analysis"],)),
        "draw": (migration_default_model_roles["image_generation"], (migration_default_model_roles["image_generation"],)),
    }
    image_model_groups = resolve_image_model_groups(
        models_config=models_config,
        builtin_groups=resolved_builtin_groups,
        config_path=config_path,
    )
    image_role_models: dict[str, str] = {}
    image_role_sources: dict[str, str] = {}
    image_model_role_overrides: dict[str, str] = {}
    for role_name in IMAGE_MODEL_ROLE_NAMES:
        group_id = image_model_group_for_role(role_name)
        group = image_model_groups[group_id]
        role_model, role_source = resolve_model_role_assignment_fn(
            role_name=role_name,
            config_path_suffix=f"models.{role_name}",
            new_env_name=f"DOCX_AI_MODELS_{role_name.upper()}_DEFAULT",
            new_role_config=parse_optional_config_section_fn(models_config, role_name, parent_name="models"),
            fallback_value=group["default"],
            fallback_source=f"{IMAGE_MODEL_GROUP_SOURCE_PREFIX}{group_id}<-{group['default_source']}",
        )
        image_role_models[role_name] = role_model
        image_role_sources[role_name] = role_source
        if not role_source.startswith(IMAGE_MODEL_GROUP_SOURCE_PREFIX):
            image_model_role_overrides[role_name] = role_model

    models = model_registry_factory_fn(
        text=text_model_config,
        boundary_review=boundary_review_model,
        **image_role_models,
    )
    model_sources = {
        "text.default": text_default_source,
        "text.options": text_options_source,
        "boundary_review": boundary_review_model_source,
        **image_role_sources,
    }
    emit_legacy_model_config_warnings_fn(config_data, model_sources)

    return {
        "default_model": default_model,
        "models": models,
        "model_sources": model_sources,
        "image_vision_model_default": image_model_groups["vision"]["default"],
        "image_vision_model_options": tuple(image_model_groups["vision"]["options"]),
        "image_draw_model_default": image_model_groups["draw"]["default"],
        "image_draw_model_options": tuple(image_model_groups["draw"]["options"]),
        "image_model_role_overrides": image_model_role_overrides,
    }
