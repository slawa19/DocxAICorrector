# Контракт: конфиг, профили и контракт вызова аудиокниги (FR-001, FR-002, FR-008)

## 1. Ключи конфига

| Ключ | Было | Стало |
|---|---|---|
| `audiobook_postprocess_default` (TOML, верхний уровень) | bool, по умолчанию `false` (`core/config_runtime_sections.py:528`) | **удалён**; оставленный в пользовательском `config.toml` → WARNING `config_key_ignored` (механизм `ReadTrackingConfigData`, `core/config.py:1122`); гард `tests/test_config_keys_are_read.py` не ослабляется и не получает исключения |
| `DOCX_AI_AUDIOBOOK_POSTPROCESS_DEFAULT` (env) | bool (`core/config_runtime_sections.py:574-576`) | **удалён** (без псевдонима) |
| `[models.audiobook].default` | модель удаляемого второго прохода (единственный потребитель `narration_postprocess.py:291`) | модель режима `audiobook`: основной вызов и исправление (FR-008) |
| `enable_paragraph_markers` | общий | для `audiobook` не читается: режим всегда маркерный (research R12, О-3) |
| `editorial_intensity_default` | добавлялась к промпту аудиокниги (`pipeline/support.py:35`) | для `audiobook` не читается (FR-004) |
| `source_language_default`, `target_language_default` | подставлялись для `audiobook` | для `audiobook` не читаются (FR-001) |

## 2. Резолвер модели (одна функция для UI и раннера)

`core/audiobook_mode.resolve_audiobook_model(app_config, *, requested_model, origin) -> AudiobookModelResolution`:

1. `requested_model` непустой → он (`source="requested"`); UI — значение селектора модели режима аудиокниги, раннер —
   `run_profile.model`;
2. иначе `app_config["audiobook_model"]` (`source="config"`), который загрузчик уже вычислил как
   `[models.audiobook].default`, а без раздела — `[models.text].default`
   (`core/config_runtime_sections.py:442-474`), и проверил на `responses_text` (`core/config.py:1491-1496`).

Для `translate`/`edit` резолвер не вызывается (их модель — как сейчас и спека 069).

## 3. Пара языков

`core/audiobook_mode.language_pair_for_operation(operation, source, target) -> (str | None, str | None)`:
`("audiobook", *, *) → (None, None)`; иначе — входные значения без изменений (нормализацию `translate`/`edit` не трогаем).
Вызывают: `ui/_app.py` (после сайдбара, до записи в `app_config`, `:1047-1049`), `processing/processing_runtime.py`
(маркер подготовки `:1678`, старт `:2090-2092`), `pipeline/setup.py:174-175`, `pipeline/_pipeline.py:989-990`,
`validation/profiles.py:314-315`. `ProcessingContext.source_language/target_language` (`pipeline/contracts.py:246-247`) —
`str | None`. Отчёт раннера хранит `null`, не `""` и не `en/ru`; язык интерфейса отчёта
(`_resolve_reader_mvp_status_language`, `run_lietaer_validation.py:725`) для `audiobook` берётся из языка UI по
умолчанию, а не из пары произведения.

`core/models.LANGUAGE_CHANGING_OPERATIONS` (`:37`) = `{"translate"}`. `pipeline/footnote_markers.py:355-356` по-прежнему
пропускает `audiobook` по имени операции (не по множеству) — тест закрепляет.

## 4. Профили `corpus_registry.toml`

- Удаляется профиль `ui-parity-translate-audiobook-postprocess` (`:151-160`) и поле `audiobook_postprocess_enabled`
  во всех профилях, где оно есть (перечень — ревью Codex, таблица FR-002, строки сверить на `fdf775f`).
- `ui-parity-standalone-audiobook` (`:175-182`): без `source_language`/`target_language`; комментарий над ним
  переписывается: вход — переведённый документ.
- WP-H: документные профили `audiobook-rm-ch3-translated`, `audiobook-money-ch3-translated`,
  `audiobook-money-full-standard-translated` (входы — research R13; решение о коммите — владелец, T-H0).
