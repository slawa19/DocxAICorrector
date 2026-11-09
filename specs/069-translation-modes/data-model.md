# Data Model: спека 069

Сущности и их поля; где живут и кто пишет. Контракты форматов — в [contracts/](contracts/).

## 1. Конфигурация режимов (WP-1, `core/translation_modes.py`)

### `TranslationPassSpec` (frozen)

| Поле | Тип | Правило |
|---|---|---|
| `model` | `str` | селектор модели (`openrouter:…`, `anthropic:…`, голый id); валиден для `responses_text` (`resolve_model_selector`) |
| `editorial_intensity` | `str \| None` | `conservative \| literary` (ключи `_PROMPT_EDITORIAL_INTENSITY_PATHS`); только у первого прохода; `None` → `editorial_intensity_default` |
| `reasoning_effort` | `str \| None` | `minimal \| low \| medium \| high`; `None` — параметра в запросе нет |

### `TranslationModeSpec` (frozen)

| Поле | Тип | Правило |
|---|---|---|
| `name` | `Literal["standard", "quality"]` | ключ раздела `[translation_modes.<name>]` |
| `first_pass` | `TranslationPassSpec` | обязателен |
| `polish_pass` | `TranslationPassSpec \| None` | есть только если задан `polish_model`; интенсивность не применяется (промпт `literary_polish` фиксирует `literary`, `core/config.py:1706-1709`) |

### `TranslationModesConfig` (frozen) — часть `AppConfig`

`default_mode: Literal["standard", "quality"]` (`translation_mode_default`), `modes: Mapping[str, TranslationModeSpec]`.
`single` в конфиге не описывается — это «нынешний один проход», он строится из общих `[models.text]` и
`editorial_intensity_default`.

### `EffectiveTranslationConfig` (frozen) — результат единого разрешения

| Поле | Тип | Источник |
|---|---|---|
| `mode` | `Literal["standard", "quality", "single"]` | запрос (UI-радио / поле профиля) или `default_mode` |
| `first_pass` | `TranslationPassSpec` (с разрешёнными `model`, `editorial_intensity`) | режим; для `single` — запрошенные/общие значения |
| `polish_pass` | `TranslationPassSpec \| None` | режим; `single` и `quality` — `None` |
| `overridden_settings` | `tuple[str, ...]` | имена полей, которые режим переопределил (`model`, `editorial_intensity`); идут в WARNING |
| `origin` | `str` | `ui` или `run_profile:<id>` |

Ключи, которые `apply_effective_translation_config` пишет в `app_config` прогона (читает конвейер и отчёт):
`model`, `editorial_intensity_default`, `translation_mode`, `translation_first_pass_model`,
`translation_first_pass_reasoning_effort`, `translation_polish_model`, `translation_polish_reasoning_effort`
(`None` → ключ со значением `None`, не отсутствует — отчёт видит «нет второго прохода» явно).

`ResolvedRuntimeConfig` (`validation/profiles.py:148`) получает `translation_mode`,
`translation_first_pass_model`, `translation_first_pass_reasoning_effort`, `translation_polish_model`,
`translation_polish_reasoning_effort` (для `edit`/`audiobook` — `None`).

`RunProfile` получает `translation_mode: str | None` (`standard | quality | single`; иное — ошибка загрузки реестра).

## 2. Профиль запроса (WP-2, `generation/_generation.py`)

### `GenerationRequestProfile` (frozen)

| Поле | Тип | По умолчанию | Смысл |
|---|---|---|---|
| `reasoning_effort` | `str \| None` | `None` | ставит `reasoning` (Responses) / `extra_body.reasoning` (Chat); Anthropic — нет |
| `output_budget_multiplier` | `float` | `1.0` | множитель к `max((len // 3) * 4, 512)` и формуле глоссария; потолок прежний |
| `usage_stage` | `str` | `text_generation` | стадия бухгалтерии ответов (`glossary_extraction`, `literary_polish`) |

`DEFAULT_REQUEST_PROFILE` = все значения по умолчанию; при нём запросы побайтно прежние (SC-006).

### Таблица множителей (WP-2, `generation/output_budget.py`)

`MODEL_OUTPUT_BUDGET_MULTIPLIERS: Mapping[str, float]` — ключ: канонический id модели без провайдера
(`google/gemini-3.7-flash`); значение > 0; неизвестная модель → 1,0. Каждая запись — с комментарием происхождения
(прогон, дата, p99/лимит). `output_budget_multiplier(model_selector) -> float`.

## 3. Учёт (WP-3, `core/model_accounting.py`)

### `ModelCallUsage` — новые поля

| Поле | Тип | Откуда | Отсутствие |
|---|---|---|---|
| `reasoning_tokens` | `int \| None` | `usage.output_tokens_details.reasoning_tokens` (Responses), `usage.completion_tokens_details.reasoning_tokens` (Chat) | `None` — «неизвестно» |
| `cached_tokens` | `int \| None` | `usage.input_tokens_details.cached_tokens` / `usage.prompt_tokens_details.cached_tokens` | `None` |
| `cache_write_tokens` | `int \| None` | `usage.prompt_tokens_details.cache_write_tokens` (если провайдер отдаёт) | `None` |
| `cache_discount_usd` | `float \| None` | `usage.cache_discount` (OpenRouter, если отдаёт) | `None` |

Чисел не придумывает (контракт `:12-22`): только чтение полей ответа.

### `_StageTotals` — новые поля

`reasoning_tokens` (сумма известных), `reasoning_reported_call_count`, `reasoning_unreported_call_count`,
`cached_tokens`, `cache_write_tokens`, `cache_discount_usd`, `cache_fields_reported_call_count`.

### `LiteraryPolishCounters` (раздел снимка `literary_polish`)

| Поле | Тип |
|---|---|
| `sent_block_count`, `sent_paragraph_count` | `int` |
| `accepted_paragraph_count` | `int` |
| `rolled_back_paragraph_count` | `int` |
| `rollback_reason_counts` | `dict[str, int]` — ключи из `contracts/literary-polish-rollbacks.schema.json` (`reason`) |
| `block_rollback_count` | `int` |
| `failed_block_count`, `failed_reason_counts` | `int`, `dict[str, int]` (`error`, `stopped`, `empty`) |
| `skipped_paragraph_counts` | `dict[str, int]` — `not_accepted`, `non_target_script`, `unmarked_block` |
| `generator_counters` | вложенный снимок счётчиков генератора, записанных внутри `pass_counter_scope` (disposition, повторы, путь API, удаления текста) |
| `artifact_path` | `str \| None` |

`pass_counter_scope(name)` — контекстный менеджер; внутри него все `record_*`, кроме `record_model_call_usage`,
пишутся в `generator_counters` раздела `name`; `record_model_call_usage` пишет в стадию по `usage_stage` как
всегда. Вложенность — стек; выход по исключению восстанавливает предыдущую область.

## 4. Второй проход (WP-4, WP-6)

### `PolishCheckResult` (WP-4, `text/polish_checks.py`)

`fired: tuple[str, ...]` (коды `numbers_changed`, `new_non_target_script_word`, `lost_non_target_script_word`,
`mixed_script_word`, `list_prefix_changed`, `footnote_marker_lost`, `length_ratio_out_of_bounds`), `details:
Mapping[str, object]` (что именно: потерянные/добавленные токены, слова, префиксы, отношение длин). Функция
`check_polished_paragraph(first_pass: str, candidate: str, *, target_language: str) -> PolishCheckResult` — чистая.
Константы: `LENGTH_RATIO_MIN = 0.70`, `LENGTH_RATIO_MAX = 1.50`, `TARGET_SCRIPT_MIN_SHARE = 0.5` (для отбора О-1).

### `PolishParagraphOutcome` / `PolishBlockOutcome` (WP-6, `pipeline/literary_polish.py`)

- абзац: `paragraph_id`, `first_pass_text`, `candidate_text | None`, `final_text`, `decision` (`accepted |
  rolled_back | skipped`), `reasons: tuple[str, ...]`;
- блок: `processed_chunk` (итоговый `MarkerPreservedBlockText` или `str`), `paragraphs`, `block_rolled_back: bool`,
  `failure: str | None`, `stopped: bool`.

Переходы: `skipped` ← не `accepted` / доля целевого письма < 0,5 / многоабзацный блок без маркеров; `accepted` ← ответ
`accepted` и ни одного срабатывания; `rolled_back` ← срабатывание, ответ не `accepted`, несовпадение маркеров блока,
исключение, Stop. Статус абзаца в записи блока (`ParagraphDisposition.status`) не меняется ни в одном переходе.

### Строка артефакта откатов

`contracts/literary-polish-rollbacks.schema.json`. Файл: `.run/literary_polish_rollbacks/<run_id>.jsonl`; срок и число —
`LITERARY_POLISH_ROLLBACKS_MAX_AGE_SECONDS = 7 дней`, `LITERARY_POLISH_ROLLBACKS_MAX_COUNT = 400`
(`runtime/artifact_retention.py`).

### Состояние и инициализация (WP-6, `pipeline/contracts.py`)

`ProcessingState` (`pipeline/contracts.py:254`): `polish_system_prompt: str | None = None`, `stopped_during_polish: bool = False`,
`last_delivered_block_text: str = ""` (хвост для контекста второго прохода).
`ProcessingInitialization` (`:325`): `polish_client: object | None = None`, `polish_model_id: str | None = None`.

## 5. Оценка цены (WP-7, WP-8)

### `CoefficientTable` (`resources/cost_estimate_coefficients.json`)

Формат — `contracts/cost-estimate.md`: `version`, `frozen_at`, `anchor` (модель, пара, формулы ввода/вывода по форме
документа с происхождением), `glossary` (константы книги с вилкой), `ratios[]` (модель × стадия × пара → отношение к
якорю ввода и вывода, происхождение), `discount_scenarios[]` (модель → множитель нижней границы, происхождение).

### `EstimateInput`

`llm_job_count`, `paragraph_count`, `source_chars`, `source_language`, `target_language`, `passes[]` (`model`, `stage`,
`reasoning_effort`).

### `PriceList`

`fetched_at` (ISO-8601), `source` (`network | cache`), `prices: Mapping[model_id, (input_per_1m, output_per_1m)]`.

### `CostEstimate`

`mode`, `coefficients_version`, `price_list_date | None`, `stages: Mapping[stage, StageEstimate]` (`input_tokens`,
`output_tokens`, `upper_usd | None`, `lower_usd | None`, `discount_scenario: str | None`), `total_upper_usd | None`,
`total_lower_usd | None`, `excludes: ["images"]`, `extrapolated: bool`, `price_unknown_models: tuple[str, ...]`.

### `CostEstimateSnapshot`

`contracts/cost-estimate-snapshot.schema.json`. Замораживается при «Старт» (UI) / до прогона (раннер); живёт в
`app_config["cost_estimate_snapshot"]`, в bundle (`cost_estimate_snapshot`) и в отчёте раннера.

### `CostActual` (в bundle и событии)

`stages: Mapping[stage, cost_usd_reported_by_provider]` для `glossary_extraction`, `text_generation`,
`literary_polish`; `total_usd`; `cost_accounting_complete: bool`; `run_complete: bool`.
