"""Spec 069 FR-001: translation modes, their config contract and the one resolution function.

Pure module: no Streamlit, no network, no import of ``core.config`` at import time (the
config loader imports this module, so validators come in as parameters). The contract is
``specs/069-translation-modes/contracts/translation-modes-config.md``.

Two modes are configured (``[translation_modes.standard]`` and ``[translation_modes.quality]``);
a third, ``single``, is not configured: it is "the pre-069 single pass" and is built from the
shared ``[models.text]`` default and ``editorial_intensity_default``. For ``translate`` the
mode WINS over the requested model and intensity; ``edit`` and ``audiobook`` are not touched.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Literal, cast

from docxaicorrector.core.logger import log_event

CONFIGURED_MODE_NAMES = ("standard", "quality")
REQUESTABLE_MODE_NAMES = ("standard", "quality", "single")
REASONING_EFFORT_VALUES = ("minimal", "low", "medium", "high")
DEFAULT_TRANSLATION_MODE = "standard"

_DEFAULT_MODE_ENV = "DOCX_AI_TRANSLATION_MODE_DEFAULT"
_MODE_ENV_PREFIX = "DOCX_AI_TRANSLATION_MODES_"
_ENV_CLEAR_VALUE = "none"
_SECTION_FIELDS = (
    "model",
    "editorial_intensity",
    "reasoning_effort",
    "polish_model",
    "polish_reasoning_effort",
)


@dataclass(frozen=True)
class TranslationPassSpec:
    model: str
    editorial_intensity: str | None = None
    reasoning_effort: str | None = None


@dataclass(frozen=True)
class TranslationModeSpec:
    name: str
    first_pass: TranslationPassSpec
    polish_pass: TranslationPassSpec | None = None


@dataclass(frozen=True)
class TranslationModesConfig:
    default_mode: str
    modes: Mapping[str, TranslationModeSpec]
    # "<mode>.<field>" / "default" -> "toml" | "env" | "default"; feeds ``translation_modes_resolved``.
    sources: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class EffectiveTranslationConfig:
    mode: Literal["standard", "quality", "single"]
    first_pass: TranslationPassSpec
    polish_pass: TranslationPassSpec | None
    overridden_settings: tuple[str, ...]
    origin: str

    def to_runtime_fields(self) -> dict[str, object]:
        """The ``translation_*`` keys of ``apply_effective_translation_config`` (``None`` = no such pass)."""
        polish = self.polish_pass
        return {
            "translation_mode": self.mode,
            "translation_first_pass_model": self.first_pass.model,
            "translation_first_pass_reasoning_effort": self.first_pass.reasoning_effort,
            "translation_polish_model": polish.model if polish is not None else None,
            "translation_polish_reasoning_effort": polish.reasoning_effort if polish is not None else None,
        }


def _read_text(value: object, *, name: str, source_name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise RuntimeError(f"Некорректное поле {name} в {source_name}: ожидается строка.")
    stripped = value.strip()
    return stripped or None


def _env_text(environ: Mapping[str, str], name: str) -> str | None:
    raw = environ.get(name, "").strip()
    return raw or None


def _check_reasoning(value: str | None, *, name: str) -> str | None:
    if value is None:
        return None
    normalized = value.lower()
    if normalized not in REASONING_EFFORT_VALUES:
        raise RuntimeError(
            f"Некорректное значение {name}: {value}. Ожидалось одно из: {', '.join(REASONING_EFFORT_VALUES)}."
        )
    return normalized


def load_translation_modes(
    config_data: Mapping[str, object],
    *,
    environ: Mapping[str, str],
    editorial_intensity_values: tuple[str, ...],
    validate_model_fn: Callable[[str, str], None],
    source_name: str,
) -> TranslationModesConfig:
    """Read ``translation_mode_default`` and ``[translation_modes.*]``: TOML first, then the environment.

    Only ``.get`` is used on the tables, so ``ReadTrackingConfigData`` reports every key this
    function does not read (``config_key_ignored``). A config without any mode (no section, no
    env value) loads with empty ``modes``: asking for a mode then fails in the resolver.
    """
    modes_table = config_data.get("translation_modes")
    if modes_table is None:
        modes_table = {}
    if not isinstance(modes_table, Mapping):
        raise RuntimeError(f"Некорректное поле translation_modes в {source_name}: ожидается таблица.")
    unknown_sections = sorted(str(key) for key in modes_table.keys() if key not in CONFIGURED_MODE_NAMES)
    if unknown_sections:
        raise RuntimeError(
            f"Неизвестные режимы перевода в {source_name}: {', '.join(unknown_sections)}. "
            f"Допустимы: {', '.join(CONFIGURED_MODE_NAMES)}."
        )

    sources: dict[str, str] = {}
    default_value = _read_text(
        config_data.get("translation_mode_default"), name="translation_mode_default", source_name=source_name
    )
    sources["default"] = "toml" if default_value is not None else "default"
    env_default = _env_text(environ, _DEFAULT_MODE_ENV)
    if env_default is not None:
        default_value, sources["default"] = env_default, "env"
    default_mode = (default_value or DEFAULT_TRANSLATION_MODE).lower()
    if default_mode not in CONFIGURED_MODE_NAMES:
        raise RuntimeError(
            f"Некорректное значение translation_mode_default: {default_mode}. "
            f"Допустимы: {', '.join(CONFIGURED_MODE_NAMES)}."
        )

    modes: dict[str, TranslationModeSpec] = {}
    for mode_name in CONFIGURED_MODE_NAMES:
        section = modes_table.get(mode_name)
        if section is not None and not isinstance(section, Mapping):
            raise RuntimeError(f"Некорректное поле translation_modes.{mode_name} в {source_name}: ожидается таблица.")
        values: dict[str, str | None] = {}
        for field_name in _SECTION_FIELDS:
            toml_value = None
            if section is not None:
                toml_value = _read_text(
                    section.get(field_name),
                    name=f"translation_modes.{mode_name}.{field_name}",
                    source_name=source_name,
                )
            env_name = f"{_MODE_ENV_PREFIX}{mode_name.upper()}_{field_name.upper()}"
            env_value = _env_text(environ, env_name)
            if env_value is not None:
                cleared = env_value.lower() == _ENV_CLEAR_VALUE
                values[field_name] = None if cleared else env_value
                sources[f"{mode_name}.{field_name}"] = "env"
            else:
                values[field_name] = toml_value
                sources[f"{mode_name}.{field_name}"] = "toml" if toml_value is not None else "default"
        declared = section is not None or any(
            source != "default" for key, source in sources.items() if key.startswith(f"{mode_name}.")
        )
        if not declared:
            continue
        modes[mode_name] = _build_mode_spec(
            mode_name,
            values,
            editorial_intensity_values=editorial_intensity_values,
            validate_model_fn=validate_model_fn,
        )

    if modes and default_mode not in modes:
        raise RuntimeError(
            f"translation_mode_default указывает на режим {default_mode}, но раздела "
            f"[translation_modes.{default_mode}] в {source_name} нет."
        )
    return TranslationModesConfig(default_mode=default_mode, modes=modes, sources=sources)


def _build_mode_spec(
    mode_name: str,
    values: Mapping[str, str | None],
    *,
    editorial_intensity_values: tuple[str, ...],
    validate_model_fn: Callable[[str, str], None],
) -> TranslationModeSpec:
    prefix = f"translation_modes.{mode_name}"
    model = values["model"]
    if model is None:
        raise RuntimeError(f"В режиме перевода {mode_name} не задан {prefix}.model.")
    validate_model_fn(model, f"{prefix}.model")
    intensity = values["editorial_intensity"]
    if intensity is not None:
        intensity = intensity.lower()
        if intensity not in editorial_intensity_values:
            raise RuntimeError(
                f"Некорректное значение {prefix}.editorial_intensity: {intensity}. "
                f"Ожидалось одно из: {', '.join(editorial_intensity_values)}."
            )
    reasoning = _check_reasoning(values["reasoning_effort"], name=f"{prefix}.reasoning_effort")
    polish_model = values["polish_model"]
    polish_reasoning = _check_reasoning(values["polish_reasoning_effort"], name=f"{prefix}.polish_reasoning_effort")
    polish_pass: TranslationPassSpec | None = None
    if polish_model is not None:
        validate_model_fn(polish_model, f"{prefix}.polish_model")
        polish_pass = TranslationPassSpec(model=polish_model, editorial_intensity=None, reasoning_effort=polish_reasoning)
    elif polish_reasoning is not None:
        raise RuntimeError(f"{prefix}.polish_reasoning_effort задан без {prefix}.polish_model.")
    return TranslationModeSpec(
        name=mode_name,
        first_pass=TranslationPassSpec(model=model, editorial_intensity=intensity, reasoning_effort=reasoning),
        polish_pass=polish_pass,
    )


def log_translation_modes_resolved(modes_config: TranslationModesConfig) -> None:
    """DEBUG ``translation_modes_resolved``: the effective values and where each one came from."""
    log_event(
        logging.DEBUG,
        "translation_modes_resolved",
        "Режимы перевода разрешены.",
        default_mode=modes_config.default_mode,
        modes={
            name: {
                "model": spec.first_pass.model,
                "editorial_intensity": spec.first_pass.editorial_intensity,
                "reasoning_effort": spec.first_pass.reasoning_effort,
                "polish_model": spec.polish_pass.model if spec.polish_pass else None,
                "polish_reasoning_effort": spec.polish_pass.reasoning_effort if spec.polish_pass else None,
            }
            for name, spec in modes_config.modes.items()
        },
        sources=dict(modes_config.sources),
    )


def _config_value(app_config: Mapping[str, object], key: str) -> object:
    try:
        return app_config[key]
    except KeyError:
        return None


def resolve_effective_translation_config(
    app_config: Mapping[str, object],
    *,
    processing_operation: str,
    requested_mode: str | None,
    requested_model: str | None,
    requested_intensity: str | None,
    origin: str,
) -> EffectiveTranslationConfig | None:
    """The single place that decides the effective translation configuration (UI and runner).

    ``None`` for any operation but ``translate``. ``standard`` / ``quality`` take model,
    intensity and reasoning from the mode; an explicit ``requested_model`` /
    ``requested_intensity`` that differs is overridden with a WARNING naming the fields.
    ``single`` is the pre-069 single pass: requested (or shared default) model and intensity,
    no reasoning, no second pass.
    """
    if processing_operation != "translate":
        if requested_mode:
            log_event(
                logging.WARNING,
                "translation_mode_ignored_for_operation",
                "Режим перевода задан для операции, не являющейся переводом, и игнорируется.",
                origin=origin,
                translation_mode=requested_mode,
                processing_operation=processing_operation,
            )
        return None

    modes_config = _modes_config_from(app_config)
    mode_name = (requested_mode or modes_config.default_mode).strip().lower()
    if mode_name not in REQUESTABLE_MODE_NAMES:
        raise RuntimeError(
            f"Неизвестный режим перевода: {mode_name}. Допустимы: {', '.join(REQUESTABLE_MODE_NAMES)}."
        )

    if mode_name == "single":
        from docxaicorrector.core.config import get_text_model_default

        model = requested_model or get_text_model_default(app_config)
        intensity = requested_intensity or str(_config_value(app_config, "editorial_intensity_default") or "literary")
        return EffectiveTranslationConfig(
            mode="single",
            first_pass=TranslationPassSpec(model=model, editorial_intensity=intensity, reasoning_effort=None),
            polish_pass=None,
            overridden_settings=(),
            origin=origin,
        )

    spec = modes_config.modes.get(mode_name)
    if spec is None:
        raise RuntimeError(
            f"Режим перевода {mode_name} не настроен: в config.toml нет раздела [translation_modes.{mode_name}]."
        )
    first_pass = spec.first_pass
    effective_intensity = first_pass.editorial_intensity
    if effective_intensity is None:
        effective_intensity = str(_config_value(app_config, "editorial_intensity_default") or "literary")
    overridden: list[str] = []
    if requested_model and requested_model != first_pass.model:
        overridden.append("model")
    if requested_intensity and requested_intensity != effective_intensity:
        overridden.append("editorial_intensity")
    if overridden:
        log_event(
            logging.WARNING,
            "translation_mode_overrides_setting",
            "Режим перевода переопределил заданные настройки.",
            origin=origin,
            translation_mode=mode_name,
            fields=list(overridden),
            requested_model=requested_model,
            requested_editorial_intensity=requested_intensity,
        )
    return EffectiveTranslationConfig(
        mode=mode_name,  # type: ignore[arg-type]
        first_pass=TranslationPassSpec(
            model=first_pass.model,
            editorial_intensity=effective_intensity,
            reasoning_effort=first_pass.reasoning_effort,
        ),
        polish_pass=spec.polish_pass,
        overridden_settings=tuple(overridden),
        origin=origin,
    )


def _modes_config_from(app_config: Mapping[str, object]) -> TranslationModesConfig:
    modes = _config_value(app_config, "translation_modes")
    default_mode = _config_value(app_config, "translation_mode_default")
    return TranslationModesConfig(
        default_mode=str(default_mode or DEFAULT_TRANSLATION_MODE),
        modes=modes if isinstance(modes, Mapping) else {},
    )


def apply_effective_translation_config(
    app_config: Mapping[str, object], effective: EffectiveTranslationConfig | None
) -> dict[str, object]:
    """A copy of ``app_config`` as a dict with the effective translation fields written in.

    ``None`` (edit / audiobook) returns the copy unchanged. A missing second pass is written as
    ``None`` rather than left out, so a report sees "no second pass" explicitly.
    """
    to_dict = getattr(app_config, "to_dict", None)
    applied: dict[str, object] = dict(cast(Mapping[str, object], to_dict())) if callable(to_dict) else dict(app_config)
    if effective is None:
        return applied
    applied["model"] = effective.first_pass.model
    if effective.first_pass.editorial_intensity is not None:
        applied["editorial_intensity_default"] = effective.first_pass.editorial_intensity
    applied.update(effective.to_runtime_fields())
    return applied
