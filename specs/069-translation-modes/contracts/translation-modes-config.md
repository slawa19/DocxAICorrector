# Контракт: конфигурация режимов перевода

Владелец: WP-1 (`core/translation_modes.py`). Читатели: `ui/_app.py`, `validation/profiles.py`, конвейер (через ключи
`app_config`), отчёт раннера.

## 1. `resources/config.toml`

```toml
# Spec 069: режимы операции translate. Модели и уровни — по замеру bake-off FR-017 (спека 063), не ручка UI.
translation_mode_default = "standard"          # "standard" | "quality"

[translation_modes.standard]
model = "openrouter:google/gemini-3.1-flash-lite-preview"   # первый проход
editorial_intensity = "literary"                            # первый проход
# reasoning_effort = ""                                     # первый проход: не задан -> параметра в запросе нет
polish_model = "openrouter:anthropic/claude-haiku-5.5"      # второй проход literary_polish
# polish_reasoning_effort = ""                              # не задан -> как в замере C (без параметра)

[translation_modes.quality]
model = "openrouter:google/gemini-3.7-flash"
editorial_intensity = "conservative"
reasoning_effort = "low"
# polish_model отсутствует -> второго прохода нет
```

| Ключ | Тип | Обязателен | Допустимо |
|---|---|---|---|
| `translation_mode_default` | str | да | `standard`, `quality` |
| `[translation_modes.<mode>].model` | str | да | селектор, валидный для `responses_text` |
| `.editorial_intensity` | str | нет | `conservative`, `literary`; нет → `editorial_intensity_default` |
| `.reasoning_effort` | str | нет | `minimal`, `low`, `medium`, `high`; пусто/нет → параметра нет |
| `.polish_model` | str | нет | селектор; нет → второго прохода нет |
| `.polish_reasoning_effort` | str | нет | как `reasoning_effort`; без `polish_model` — ошибка конфига |

Режимов ровно два раздела; третий раздел (`[translation_modes.foo]`) — ошибка загрузки, не молчаливое игнорирование.
Неизвестный ключ внутри раздела — `config_key_ignored` (механизм `ReadTrackingConfigData`, спека 066 FR-012).
Отсутствие раздела режима, на который указывает `translation_mode_default`, — ошибка загрузки.

## 2. Переменные окружения (после TOML; правило спеки 066)

| Переменная | Перекрывает |
|---|---|
| `DOCX_AI_TRANSLATION_MODE_DEFAULT` | `translation_mode_default` |
| `DOCX_AI_TRANSLATION_MODES_STANDARD_MODEL`, `…_QUALITY_MODEL` | `.model` |
| `DOCX_AI_TRANSLATION_MODES_<MODE>_EDITORIAL_INTENSITY` | `.editorial_intensity` |
| `DOCX_AI_TRANSLATION_MODES_<MODE>_REASONING_EFFORT` | `.reasoning_effort` (значение `none` → снять) |
| `DOCX_AI_TRANSLATION_MODES_<MODE>_POLISH_MODEL` | `.polish_model` (значение `none` → снять второй проход) |
| `DOCX_AI_TRANSLATION_MODES_<MODE>_POLISH_REASONING_EFFORT` | `.polish_reasoning_effort` |

Источник каждого эффективного значения (`toml` / `env`) пишется в событие `translation_modes_resolved` (DEBUG) — по
образцу `model_registry_resolved`.

## 3. Поле run-профиля (`corpus_registry.toml`)

```toml
[[run_profiles]]
id = "ui-parity-translate-benchmark-standard"
processing_operation = "translate"
translation_mode = "standard"      # "standard" | "quality" | "single"
```

- Профиль без поля → `translation_mode_default` (как UI).
- `single` → нынешний один проход: модель `run_profile.model` или `[models.text].default`, интенсивность
  `run_profile.editorial_intensity` или `editorial_intensity_default`, без `reasoning`, без второго прохода.
- Для `standard`/`quality` поля `model` и `editorial_intensity` профиля проигрывают режиму; если они заданы и
  отличаются — WARNING `translation_mode_overrides_setting` (см. `events.md`).
- Для `edit`/`audiobook` поле игнорируется (и даёт WARNING `translation_mode_ignored_for_operation`, если задано).
- Регрессионные профили (17 translate-профилей на `64f8856`) получают `translation_mode = "single"` явно; гард-тест
  требует явного поля у каждого translate-профиля реестра.

## 4. Единое разрешение

```python
def resolve_effective_translation_config(
    app_config: Mapping[str, object],
    *,
    processing_operation: str,
    requested_mode: str | None,
    requested_model: str | None,
    requested_intensity: str | None,
    origin: str,                      # "ui" | "run_profile:<id>"
) -> EffectiveTranslationConfig | None: ...

def apply_effective_translation_config(
    app_config: Mapping[str, object], effective: EffectiveTranslationConfig | None
) -> dict[str, object]: ...
```

Инварианты: `None` для не-`translate`, и тогда `apply_…` возвращает копию `app_config` без изменений; одна функция для
UI и раннера (тест: одинаковые входы → одинаковый результат через оба пути); `EffectiveTranslationConfig` попадает в
runtime-config отчёта целиком (`translation_mode`, модели, интенсивность, рассуждение обоих проходов).
