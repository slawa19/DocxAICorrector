import logging
import os
from collections.abc import Mapping
from typing import Any


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
) -> Any:
    unique_options = dedupe_preserving_order_fn(options)
    if not unique_options:
        raise RuntimeError("Не задан ни один доступный text model в models.text.options")
    if len(unique_options) != len(options):
        raise RuntimeError("models.text.options содержит дублирующиеся значения моделей")
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
        structure_recognition=resolve_model_role_runtime_fn(config_like, "structure_recognition"),
        image_analysis=resolve_model_role_runtime_fn(config_like, "image_analysis"),
        image_validation=resolve_model_role_runtime_fn(config_like, "image_validation"),
        image_reconstruction=resolve_model_role_runtime_fn(config_like, "image_reconstruction"),
        image_generation=resolve_model_role_runtime_fn(config_like, "image_generation"),
        image_edit=resolve_model_role_runtime_fn(config_like, "image_edit"),
        image_generation_vision=resolve_model_role_runtime_fn(config_like, "image_generation_vision"),
    )


def resolve_text_model_options(
    *,
    config_data: dict[str, object],
    models_text_config: dict[str, object],
    parse_csv_env_fn: Any,
    parse_model_options_value_fn: Any,
    config_path: Any,
    migration_default_text_model_options: tuple[str, ...],
) -> tuple[tuple[str, ...], str]:
    new_env_options = parse_csv_env_fn("DOCX_AI_MODELS_TEXT_OPTIONS")
    if new_env_options is not None:
        return tuple(new_env_options), "env:canonical:DOCX_AI_MODELS_TEXT_OPTIONS"
    if "options" in models_text_config:
        return parse_model_options_value_fn(
            models_text_config.get("options"),
            source_name=f"{config_path}: models.text.options",
        ), "toml:canonical:models.text.options"
    legacy_env_options = parse_csv_env_fn("DOCX_AI_MODEL_OPTIONS")
    if legacy_env_options is not None:
        return tuple(legacy_env_options), "env:legacy:DOCX_AI_MODEL_OPTIONS"
    if "model_options" in config_data:
        return parse_model_options_value_fn(
            config_data.get("model_options"),
            source_name=f"{config_path}: model_options",
        ), "toml:legacy:model_options"
    return migration_default_text_model_options, "default:migration:text.options"


def resolve_text_default_model(
    *,
    config_data: dict[str, object],
    models_text_config: dict[str, object],
    coerce_model_name_fn: Any,
    config_path: Any,
    migration_default_text_model: str,
) -> tuple[str, str]:
    new_env_value = os.getenv("DOCX_AI_MODELS_TEXT_DEFAULT", "").strip()
    if new_env_value:
        return new_env_value, "env:canonical:DOCX_AI_MODELS_TEXT_DEFAULT"
    if "default" in models_text_config:
        return coerce_model_name_fn(
            models_text_config.get("default"),
            source_name=f"{config_path}: models.text.default",
        ), "toml:canonical:models.text.default"
    legacy_env_value = os.getenv("DOCX_AI_DEFAULT_MODEL", "").strip()
    if legacy_env_value:
        return legacy_env_value, "env:legacy:DOCX_AI_DEFAULT_MODEL"
    if "default_model" in config_data:
        return coerce_model_name_fn(
            config_data.get("default_model"),
            source_name=f"{config_path}: default_model",
        ), "toml:legacy:default_model"
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
    legacy_env_name: str | None = None,
    legacy_config_data: dict[str, object] | None = None,
    legacy_config_label: str | None = None,
    legacy_value_key: str | None = None,
) -> tuple[str, str]:
    new_env_value = os.getenv(new_env_name, "").strip()
    if new_env_value:
        return new_env_value, f"env:canonical:{new_env_name}"
    if "default" in new_role_config:
        return coerce_model_name_fn(
            new_role_config.get("default"),
            source_name=f"{config_path}: {config_path_suffix}.default",
        ), f"toml:canonical:{config_path_suffix}.default"
    if legacy_env_name:
        legacy_env_value = os.getenv(legacy_env_name, "").strip()
        if legacy_env_value:
            return legacy_env_value, f"env:legacy:{legacy_env_name}"
    if legacy_config_data is not None and legacy_value_key is not None:
        if legacy_value_key in legacy_config_data:
            source_name = legacy_config_label or legacy_value_key
            return coerce_model_name_fn(
                legacy_config_data.get(legacy_value_key),
                source_name=f"{config_path}: {source_name}",
            ), f"toml:legacy:{source_name}"
    return fallback_value, f"default:migration:{role_name}"


def log_resolved_model_registry(
    models: Any,
    model_sources: Mapping[str, str],
    *,
    emitted_model_registry_log_keys: set[str],
    log_event_fn: Any,
) -> None:
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


def emit_legacy_model_config_warnings(
    config_data: Mapping[str, object],
    model_sources: Mapping[str, str],
    *,
    legacy_toml_model_keys: tuple[str, ...],
    emitted_model_registry_log_keys: set[str],
    log_event_fn: Any,
) -> None:
    for legacy_key in legacy_toml_model_keys:
        if legacy_key in config_data:
            dedupe_key = f"legacy-key:{legacy_key}"
            if dedupe_key in emitted_model_registry_log_keys:
                continue
            emitted_model_registry_log_keys.add(dedupe_key)
            log_event_fn(
                logging.WARNING,
                "legacy_model_config_key_detected",
                "Обнаружен deprecated legacy model key в config.toml; используйте секцию [models.*].",
                legacy_key=legacy_key,
                replacement="models.text" if legacy_key in {"default_model", "model_options"} else f"models.{legacy_key.removesuffix('_model')}",
            )

    structure_recognition_config = config_data.get("structure_recognition")
    if isinstance(structure_recognition_config, Mapping) and "model" in structure_recognition_config:
        dedupe_key = "legacy-key:structure_recognition.model"
        if dedupe_key not in emitted_model_registry_log_keys:
            emitted_model_registry_log_keys.add(dedupe_key)
            log_event_fn(
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
        if dedupe_key in emitted_model_registry_log_keys:
            continue
        emitted_model_registry_log_keys.add(dedupe_key)
        warning_message = "Использован deprecated legacy model source; перейдите на canonical registry keys."
        if role_name == "image_analysis" and source_name in {
            "env:legacy:DOCX_AI_VALIDATION_MODEL",
            "toml:legacy:validation_model",
        }:
            warning_message = (
                "Использован deprecated legacy validation model source. Во время миграции он переводится в обе роли: "
                "image_analysis и image_validation. Перейдите на models.image_analysis/default и models.image_validation/default."
            )
        log_event_fn(
            logging.WARNING,
            "legacy_model_config_source_used",
            warning_message,
            role_name=role_name,
            source_name=source_name,
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
) -> dict[str, Any]:
    models_config = parse_optional_config_section_fn(config_data, "models")
    models_text_config = parse_optional_config_section_fn(models_config, "text", parent_name="models")
    models_structure_recognition_config = parse_optional_config_section_fn(models_config, "structure_recognition", parent_name="models")
    models_image_analysis_config = parse_optional_config_section_fn(models_config, "image_analysis", parent_name="models")
    models_image_validation_config = parse_optional_config_section_fn(models_config, "image_validation", parent_name="models")
    models_image_reconstruction_config = parse_optional_config_section_fn(models_config, "image_reconstruction", parent_name="models")
    models_image_generation_config = parse_optional_config_section_fn(models_config, "image_generation", parent_name="models")
    models_image_edit_config = parse_optional_config_section_fn(models_config, "image_edit", parent_name="models")
    models_image_generation_vision_config = parse_optional_config_section_fn(models_config, "image_generation_vision", parent_name="models")

    model_options, text_options_source = resolve_text_model_options_fn(
        config_data=config_data,
        models_text_config=models_text_config,
    )
    default_model, text_default_source = resolve_text_default_model_fn(
        config_data=config_data,
        models_text_config=models_text_config,
    )
    text_model_config = build_text_model_config_fn(default_model, model_options)

    structure_recognition_config = parse_optional_config_section_fn(config_data, "structure_recognition")
    structure_recognition_model, structure_recognition_model_source = resolve_model_role_assignment_fn(
        role_name="structure_recognition",
        config_path_suffix="models.structure_recognition",
        new_env_name="DOCX_AI_MODELS_STRUCTURE_RECOGNITION_DEFAULT",
        new_role_config=models_structure_recognition_config,
        fallback_value=migration_default_model_roles["structure_recognition"],
        legacy_env_name="DOCX_AI_STRUCTURE_RECOGNITION_MODEL",
        legacy_config_data=structure_recognition_config,
        legacy_config_label="structure_recognition.model",
        legacy_value_key="model",
    )
    image_analysis_model, image_analysis_model_source = resolve_model_role_assignment_fn(
        role_name="image_analysis",
        config_path_suffix="models.image_analysis",
        new_env_name="DOCX_AI_MODELS_IMAGE_ANALYSIS_DEFAULT",
        new_role_config=models_image_analysis_config,
        fallback_value=migration_default_model_roles["image_analysis"],
        legacy_env_name="DOCX_AI_VALIDATION_MODEL",
        legacy_config_data=config_data,
        legacy_config_label="validation_model",
        legacy_value_key="validation_model",
    )
    image_validation_model, image_validation_model_source = resolve_model_role_assignment_fn(
        role_name="image_validation",
        config_path_suffix="models.image_validation",
        new_env_name="DOCX_AI_MODELS_IMAGE_VALIDATION_DEFAULT",
        new_role_config=models_image_validation_config,
        fallback_value=migration_default_model_roles["image_validation"],
        legacy_env_name="DOCX_AI_VALIDATION_MODEL",
        legacy_config_data=config_data,
        legacy_config_label="validation_model",
        legacy_value_key="validation_model",
    )
    image_reconstruction_model, image_reconstruction_model_source = resolve_model_role_assignment_fn(
        role_name="image_reconstruction",
        config_path_suffix="models.image_reconstruction",
        new_env_name="DOCX_AI_MODELS_IMAGE_RECONSTRUCTION_DEFAULT",
        new_role_config=models_image_reconstruction_config,
        fallback_value=migration_default_model_roles["image_reconstruction"],
        legacy_env_name="DOCX_AI_RECONSTRUCTION_MODEL",
        legacy_config_data=config_data,
        legacy_config_label="reconstruction_model",
        legacy_value_key="reconstruction_model",
    )
    image_generation_model, image_generation_model_source = resolve_model_role_assignment_fn(
        role_name="image_generation",
        config_path_suffix="models.image_generation",
        new_env_name="DOCX_AI_MODELS_IMAGE_GENERATION_DEFAULT",
        new_role_config=models_image_generation_config,
        fallback_value=migration_default_model_roles["image_generation"],
    )
    image_edit_model, image_edit_model_source = resolve_model_role_assignment_fn(
        role_name="image_edit",
        config_path_suffix="models.image_edit",
        new_env_name="DOCX_AI_MODELS_IMAGE_EDIT_DEFAULT",
        new_role_config=models_image_edit_config,
        fallback_value=migration_default_model_roles["image_edit"],
    )
    image_generation_vision_model, image_generation_vision_model_source = resolve_model_role_assignment_fn(
        role_name="image_generation_vision",
        config_path_suffix="models.image_generation_vision",
        new_env_name="DOCX_AI_MODELS_IMAGE_GENERATION_VISION_DEFAULT",
        new_role_config=models_image_generation_vision_config,
        fallback_value=migration_default_model_roles["image_generation_vision"],
    )

    models = model_registry_factory_fn(
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
    emit_legacy_model_config_warnings_fn(config_data, model_sources)

    return {
        "default_model": default_model,
        "models": models,
        "model_sources": model_sources,
        "structure_recognition_config": structure_recognition_config,
    }