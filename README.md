# DocxAICorrector

DocxAICorrector — это Streamlit-приложение для литературного редактирования `.docx` и legacy `.doc` через OpenAI с промежуточным Markdown и обратной сборкой в `.docx` через Pandoc.

Проект ориентирован на длинные документы, где редактирование по одному абзацу дает слабый результат. Вместо этого приложение собирает смысловые блоки, добавляет соседний контекст только для понимания смысла и возвращает итоговый отредактированный документ.

## Возможности

- Загрузка `.docx` и legacy `.doc` через веб-интерфейс Streamlit.
- Автоопределение legacy `.doc` и автоконвертация в рабочий `.docx` на этапе подготовки документа.
- Извлечение текста из документа с сохранением ключевой семантики структуры.
- Опциональный AI-first stage распознавания структуры документа до сборки semantic blocks: роли абзацев, heading levels, epigraph/attribution и TOC-подобные регионы.
- Сборка смысловых блоков вместо наивной обработки по одному абзацу.
- Сохранение заголовков и подзаголовков через explicit DOCX styles, AI structure recognition и fallback на консервативные эвристики.
- Сохранение нумерованных и маркированных списков, включая вложенность.
- Поддержка таблиц как самостоятельных структурных блоков с передачей в Pandoc через HTML table markup.
- Выделение подписей к изображениям и таблицам как отдельных semantic caption-блоков.
- Сохранение локального контекста через `context_before` и `context_after`.
- Последовательная обработка блоков через OpenAI Responses API.
- Retry для временных API-сбоев.
- Живой статус обработки, журнал по блокам и activity feed в UI.
- Сохранение промежуточного Markdown при частичном сбое.
- Placeholder-based pipeline для inline-изображений в `.docx`.
- Сохранение полезного inline-formatting: hyperlinks, tabs, bold, italic, underline, sup/sub.
- Safe-mode для изображений и semantic-redraw ветка с обязательным Level 1 post-check.
- Режим ручной проверки изображений: итоговый DOCX может сохранять `safe`, `candidate1` и `candidate2` для визуального сравнения.
- Compare-all режим: генерация safe, creative и conservative вариантов изображения с немедленной вставкой всех вариантов в итоговый DOCX.
- Обратная сборка Markdown в `.docx` через Pandoc с dynamic reference DOCX baseline.
- Минимальное пост-форматирование итогового DOCX: центрирование image-placeholder paragraphs, caption style/alignment и базовый table style без broad source-XML replay.
- Файловое логирование с `event_id`, контекстом и stack trace.

## Архитектура

После декомпозиции приложение разделено на независимые модули:

```text
app.py         orchestration и main()
constants.py   пути и дефолтные значения
models.py      ParagraphUnit и DocumentBlock
logger.py      логирование и user-facing ошибки
config.py      конфигурация и OpenAI client
document.py    чтение DOCX, auto-converted legacy DOC, ordered block traversal, tables/captions/headings и semantic extraction
structure_recognition.py AI-классификация структуры абзацев и enrichment role/heading metadata
generation.py  вызовы OpenAI и сборка DOCX через Pandoc/dynamic reference-doc
image_analysis.py   анализ image-assets и выбор стратегии
image_generation.py генерация candidate image и safe fallback
image_validation.py Level 1 post-check и accept/fallback decision
preparation.py   кеш подготовки документа и сборки jobs
application_flow.py orchestration idle/restart/preparation между UI и runtime
processing_service.py facade для worker/pipeline и dependency wiring обработки
workflow_state.py enum и helper-функции state-machine для UI
state.py       session_state и live status
ui.py          Streamlit-компоненты и рендеринг
tests/         регрессионные тесты ключевых контрактов

Singleton service accessor: UI должен получать processing facade через `get_processing_service()`, а не собирать dependency graph вручную.

Новые архитектурные опоры поверх базовой декомпозиции:

- `processing_runtime.py` теперь является единым normalization boundary для upload payload: он определяет реальный формат входного файла, при необходимости конвертирует legacy `.doc` в рабочий `.docx`, но для legacy `.doc` сохраняет token identity по исходным source bytes, а downstream-слоям отдаёт уже normalized payload.
- `application_flow.py`, `document.py`, `real_document_validation_structural.py` и full-tier validator используют один и тот же normalized DOCX contract вместо локальных DOCX-only assumptions.
- `preparation.py` теперь имеет отдельный structure-recognition substage между extraction и semantic-block assembly: explicit DOCX semantics остаются frozen, AI-классификация обогащает остальные абзацы, а при недоступности AI pipeline прозрачно откатывается на прежние heuristic rules.
- Real-document validation больше не является hard-coded Lietaer-only harness: registry в `corpus_registry.toml` разделяет document profiles и run profiles, а deterministic `extraction` и `structural` tiers дополняют full-tier replay path.
```

Единый актуальный source of truth по runtime workflow и image modes лежит в `docs/WORKFLOW_AND_IMAGE_MODES.md`.

Канонический source of truth по startup performance и anti-regression правилам лежит в `docs/STARTUP_PERFORMANCE_CONTRACT.md`.

Архивный раздел с historical specs, superseded design docs и review snapshots лежит в `docs/ARCHIVE_INDEX.md`.

Исторические документы по decomposition, image mode deep-dives и state/preparation refactor больше не считаются каноническими и читаются только через архивный индекс.

Спецификация hardening-а форматирования DOCX, включая headings, tables, captions и target-style baseline, лежит в `docs/DOCX_FORMATTING_HARDENING_SPEC_2026-03-13.md`.

Universal real-document validation architecture и её текущий implementation status описаны в `docs/UNIVERSAL_REAL_DOCUMENT_VALIDATION_SPEC_2026-03-21.md`.

## Как работает обработка

Минимальной единицей редактирования является не абзац, а смысловой блок:

- `target_text` — текст, который реально отправляется на редактирование.
- `context_before` — предыдущий соседний контекст только для понимания смысла.
- `context_after` — следующий соседний контекст только для понимания смысла.

Перед сборкой блоков preparation теперь проходит в два логических этапа:

- extraction и normalization извлекают абзацы, списки, таблицы, captions и базовую explicit DOCX semantics;
- optional AI structure recognition классифицирует paragraph roles и heading levels до semantic-block assembly, а при выключенном или недоступном AI остаётся прежний heuristic fallback.

Текущие правила сборки блоков:

- заголовок начинает новый блок, рендерится как markdown-heading и приклеивается хотя бы к следующему абзацу;
- последовательные элементы списка группируются вместе;
- таблица является атомарным блоком и не разваливается на обычные абзацы;
- подпись старается оставаться рядом с соседним изображением или таблицей;
- обычные абзацы объединяются до рабочего лимита `chunk_size`;
- слишком длинный абзац не режется внутри себя и уходит отдельным блоком;
- размер соседнего контекста вычисляется автоматически от `chunk_size`.

Это дает модели локальный контекст без потери управляемости: на выходе она должна вернуть только исправленный `target_text`.

Перед этим этапом upload проходит единый normalization path:

- zip-based `.docx` проходит без конвертации;
- legacy OLE `.doc` определяется автоматически и конвертируется в временный рабочий `.docx`;
- identity/token semantics для legacy `.doc` остаются привязаны к исходным source bytes, а не к bytes сконвертированного рабочего `.docx`;
- downstream preparation, extraction, validation и assembly работают только с normalized DOCX bytes, чтобы UI, background runtime и validator не drift-или по input contract.

На этапе обратной сборки итоговый DOCX опирается на два уровня поведения:

- Pandoc + dynamic reference DOCX задают основной visual baseline для headings, body text и lists;
- минимальный post-Pandoc pass форматирует captions, image-placeholder paragraphs и table baseline, а также восстанавливает прямой paragraph alignment для корректно сопоставленных абзацев без возврата к broad source paragraph XML replay.

Во время Phase 1 transition публичный callback surface сохранён для совместимости:

- `preserve_source_paragraph_properties()` остаётся mainline formatter entry point;
- `normalize_semantic_output_docx()` остаётся временным compatibility no-op и должен быть убран или сведен к internal alias не позднее конца P3 или `2026-06-30`, когда production, validation и test call sites будут переведены на основной entry point.

## Требования

- WSL2 с Linux-дистрибутивом, в котором создаётся и используется текущее `.venv`
- Python 3.11+
- Pandoc
- Для legacy `.doc`: LibreOffice (`soffice`) или fallback-связка `antiword` + `pandoc`
- OpenAI API key
- Windows PowerShell только как thin wrapper для штатных start/stop-скриптов

## Быстрый старт

Проект использует WSL-first workflow. Текущее виртуальное окружение `.venv` является Linux/WSL-окружением, поэтому `pytest`, `streamlit`, диагностические импорты и проверка зависимостей должны выполняться в WSL. PowerShell-скрипты в `scripts/` являются thin wrapper entry points для штатного запуска в WSL.

Project runtime source of truth для разработки, проверок, тестов и live-валидации — путь `/mnt/d/www/projects/2025/DocxAICorrector` внутри WSL вместе с проектной `.venv`. Не делайте выводы о зависимостях, доступности Pandoc, import health или runtime-состоянии по случайному `python`, `py`, Windows virtualenv или иному системному интерпретатору, пока не проверен project runtime. Если системный интерпретатор и project runtime расходятся, источником истины считается project runtime.

Если для вспомогательных Windows-only сценариев нужен отдельный virtualenv, используйте каталог `.venv-win/`. Это окружение допустимо для editor tooling и статического анализа вроде Pyright, но не для штатного runtime проекта. Через WSL dispatcher должны работать только lifecycle и diagnostic wrappers: `scripts/start-project.ps1`, `scripts/stop-project.ps1`, `scripts/status-project.ps1` и `scripts/tail-streamlit-log.ps1`. Не создавайте и не активируйте Windows-окружение в `.venv/`: этот путь зарезервирован за WSL-runtime проекта.

Для быстрой диагностики состояния окружения используйте `Terminal -> Run Task -> Project Status`. Эта команда одним проходом проверяет и печатает итоговый статус без ложного failed-state для обычной диагностики:

- запущен ли проект и отвечает ли health endpoint;
- есть ли WSL-окружение `.venv`;
- установлены ли Python-зависимости;
- доступен ли Pandoc для `pypandoc`;
- настроен ли `OPENAI_API_KEY`.

`Project Status` — именно диагностическая команда. Она показывает итоговый статус `READY`, `RUNNING`, `DEGRADED` или `CONFLICT`, но не должна считаться ошибкой только потому, что приложение сейчас не запущено.

### 1. Создать виртуальное окружение

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 2. Установить зависимости

```bash
pip install -r requirements.txt
```

### 3. Установить Pandoc

```bash
sudo apt-get update
sudo apt-get install -y pandoc
pandoc --version
```

### 3a. Включить автоконвертацию legacy DOC

Предпочтительный backend внутри WSL:

```bash
sudo apt-get install -y libreoffice
```

Легковесный fallback:

```bash
sudo apt-get install -y antiword pandoc
```

Если в runtime недоступен ни один backend, загрузка legacy `.doc` завершается явной ошибкой конфигурации вместо неявного сбоя на глубоком DOCX-only слое.

### 4. Настроить `.env`

```bash
cp .env.example .env
```

Минимально нужен `OPENAI_API_KEY`:

```env
OPENAI_API_KEY=sk-...
```

Поддерживаемые переменные `.env`:

- `OPENAI_API_KEY` — обязательный API-ключ OpenAI для текстовой и image-обработки.
- `DOCX_AI_MODELS_TEXT_DEFAULT` — модель редактирования текста по умолчанию.
- `DOCX_AI_MODELS_TEXT_OPTIONS` — список моделей для sidebar через запятую.
- `DOCX_AI_CHUNK_SIZE` — размер целевого блока документа.
- `DOCX_AI_MAX_RETRIES` — число retry для текстовых вызовов.
- `DOCX_AI_EDITORIAL_INTENSITY_DEFAULT` — дефолтная стилистическая интенсивность для текстовой обработки: `literary` или `conservative`. В текущем Slice 1 влияет только на prompt contract и не меняет `temperature`.
- `DOCX_AI_TRANSLATION_SECOND_PASS_DEFAULT` — включает дополнительный литературный проход после перевода по умолчанию для translate-режима.
- `DOCX_AI_TRANSLATION_SECOND_PASS_MODEL` — optional override модели для второго литературного прохода; если пусто, используется выбранная основная text model.
- `DOCX_AI_LOG_LEVEL` — уровень логирования приложения: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`; по умолчанию `INFO`, некорректное значение безопасно откатывается к `INFO` с warning-записью в лог.
- `DOCX_AI_IMAGE_MODE_DEFAULT` — режим изображений по умолчанию: `no_change`, `safe`, `semantic_redraw_direct`, `semantic_redraw_structured`, `compare_all`.
- `DOCX_AI_SEMANTIC_VALIDATION_POLICY` — политика post-check: `advisory` или `strict`.
- `DOCX_AI_KEEP_ALL_IMAGE_VARIANTS` — сохраняет в итоговом DOCX `safe`, `candidate1` и `candidate2` для ручной проверки.
- `DOCX_AI_MODELS_STRUCTURE_RECOGNITION_DEFAULT` — service-level модель optional structure recognition stage.
- `DOCX_AI_MODELS_IMAGE_ANALYSIS_DEFAULT` — service-level модель для pipeline image analysis.
- `DOCX_AI_MODELS_IMAGE_VALIDATION_DEFAULT` — service-level модель для image validator.
- `DOCX_AI_MODELS_IMAGE_RECONSTRUCTION_DEFAULT` — service-level модель для deterministic image reconstruction.
- `DOCX_AI_MODELS_IMAGE_GENERATION_DEFAULT` — service-level модель для `Images.generate`.
- `DOCX_AI_MODELS_IMAGE_EDIT_DEFAULT` — service-level модель для `Images.edit`.
- `DOCX_AI_MODELS_IMAGE_GENERATION_VISION_DEFAULT` — service-level vision model для generation-time image inspection.

Пример полного `.env`:

```env
OPENAI_API_KEY=sk-...
DOCX_AI_MODELS_TEXT_DEFAULT=gpt-5.4-mini
DOCX_AI_MODELS_TEXT_OPTIONS=gpt-5.4,gpt-5.4-mini,gpt-5-mini
DOCX_AI_CHUNK_SIZE=6000
DOCX_AI_MAX_RETRIES=3
DOCX_AI_EDITORIAL_INTENSITY_DEFAULT=literary
DOCX_AI_TRANSLATION_SECOND_PASS_DEFAULT=false
DOCX_AI_TRANSLATION_SECOND_PASS_MODEL=
DOCX_AI_MODELS_STRUCTURE_RECOGNITION_DEFAULT=gpt-5-mini
DOCX_AI_STRUCTURE_RECOGNITION_MODE=auto
DOCX_AI_STRUCTURE_VALIDATION_ENABLED=true
DOCX_AI_STRUCTURE_VALIDATION_MIN_PARAGRAPHS_FOR_AUTO_GATE=40
DOCX_AI_STRUCTURE_VALIDATION_MIN_EXPLICIT_HEADING_DENSITY=0.003
DOCX_AI_STRUCTURE_VALIDATION_MAX_SUSPICIOUS_SHORT_BODY_RATIO_WITHOUT_ESCALATION=0.05
DOCX_AI_STRUCTURE_VALIDATION_MAX_ALL_CAPS_OR_CENTERED_BODY_RATIO_WITHOUT_ESCALATION=0.03
DOCX_AI_STRUCTURE_VALIDATION_TOC_LIKE_SEQUENCE_MIN_LENGTH=4
DOCX_AI_STRUCTURE_VALIDATION_FORBID_HEADING_ONLY_COLLAPSE=true
DOCX_AI_STRUCTURE_VALIDATION_SAVE_DEBUG_ARTIFACTS=true
DOCX_AI_STRUCTURE_RECOGNITION_MIN_CONFIDENCE=medium
DOCX_AI_LOG_LEVEL=INFO
DOCX_AI_IMAGE_MODE_DEFAULT=no_change
DOCX_AI_SEMANTIC_VALIDATION_POLICY=advisory
DOCX_AI_KEEP_ALL_IMAGE_VARIANTS=false
DOCX_AI_MODELS_IMAGE_ANALYSIS_DEFAULT=gpt-5.4-mini
DOCX_AI_MODELS_IMAGE_VALIDATION_DEFAULT=gpt-5.4-mini
DOCX_AI_MODELS_IMAGE_RECONSTRUCTION_DEFAULT=gpt-5.4-mini
DOCX_AI_MODELS_IMAGE_GENERATION_DEFAULT=gpt-image-1.5
DOCX_AI_MODELS_IMAGE_EDIT_DEFAULT=gpt-image-1.5
DOCX_AI_MODELS_IMAGE_GENERATION_VISION_DEFAULT=gpt-5.4-mini
```

### 5. Запустить приложение

Вариант напрямую из WSL:

```bash
streamlit run app.py
```

Вариант через VS Code task:

1. `Terminal -> Run Task`
2. При необходимости сначала выберите `Project Status`
3. Выберите `Start Project`

Для остановки используйте `Stop Project`.

## Конфигурация

Каноническая role-based спецификация моделей лежит в `docs/specs/MODEL_ROLE_AND_CONFIGURATION_SPEC_2026-04-18.md`.

Архитектурная спецификация миграции на centralized registry реализована и сохранена как историческая запись в `docs/archive/specs/CENTRALIZED_MODEL_REGISTRY_REFACTOR_SPEC_2026-04-18.md`.

Краткая текущая матрица ролей:

| Роль | Текущая модель | Статус | Примечание |
| --- | --- | --- | --- |
| Main premium text transform | `gpt-5.4` | `recommended_high_quality` | Премиальный вариант для текстовой обработки через sidebar. |
| Main default text transform policy | `gpt-5.4-mini` | `recommended_default` | Рекомендуемый modern mini-tier по policy из `models.text.default`. |
| Budget text fallback | `gpt-5-mini` | `supported_fallback` | Текущий repository default и lower-cost fallback. |
| Structure recognition | `gpt-5-mini` | `balanced_cost_quality` | Дешевле и современнее для optional structure stage без перехода на overly-cheap nano-tier. |
| Pipeline image analysis | `gpt-5.4-mini` | `balanced_cost_quality` | Основной balanced multimodal default для routing и vision analysis. |
| Image validation | `gpt-5.4-mini` | `balanced_cost_quality` | Quality gate для post-check без цены full-tier модели. |
| Image reconstruction | `gpt-5.4-mini` | `balanced_cost_quality` | Лучший balanced choice для scene-graph extraction и text-sensitive reconstruction. |
| Image generation/edit | `gpt-image-1.5` | `balanced_cost_quality` | Обновленный image-native baseline для generation/edit ветки. |
| Generation-time image vision | `gpt-5.4-mini` | `balanced_cost_quality` | Unified vision tier для generation/edit orchestration. |

Важно:

- balanced refresh убирает `gpt-4.1-mini` из канонического sidebar shortlist; legacy compatibility может сохраняться только как временный migration input, но не как рекомендуемый новый baseline.
- analysis, validation, reconstruction и generation-time vision теперь разведены по отдельным role keys даже если часть значений совпадает.
- canonical baseline в `config.toml` теперь использует только `models.*`; legacy keys `default_model`, `model_options`, `validation_model`, `reconstruction_model` и `[structure_recognition].model` больше не являются допустимой формой для новых конфигов и примеров.
- legacy source `DOCX_AI_VALIDATION_MODEL` и top-level `validation_model` во время миграции транслируются сразу в две роли: `models.image_analysis.default` и `models.image_validation.default`, потому что исторически один key обслуживал обе стадии.
- до полного removal legacy aliases остаются только migration-compatible inputs внутри `config.py`; при их использовании loader пишет warning-события в лог, чтобы такие источники drift было легче убрать.
- removal point для legacy aliases: после текущего migration window, когда registry-only config будет считаться стабильным контрактом, loader перестанет читать legacy model keys и env aliases. Новые конфиги и automation не должны зависеть от них уже сейчас.

Базовые значения лежат в `config.toml`:

```toml
[models.text]
default = "gpt-5.4-mini"
options = ["gpt-5.4", "gpt-5.4-mini", "gpt-5-mini"]

[models.structure_recognition]
default = "gpt-5-mini"

[models.image_analysis]
default = "gpt-5.4-mini"

[models.image_validation]
default = "gpt-5.4-mini"

[models.image_reconstruction]
default = "gpt-5.4-mini"

[models.image_generation]
default = "gpt-image-1.5"

[models.image_edit]
default = "gpt-image-1.5"

[models.image_generation_vision]
default = "gpt-5.4-mini"

chunk_size = 6000
max_retries = 3
image_mode_default = "no_change"
semantic_validation_policy = "advisory"
keep_all_image_variants = false
enable_vision_image_analysis = true
enable_vision_image_validation = true
semantic_redraw_max_attempts = 2
semantic_redraw_max_model_calls_per_image = 9

[structure_recognition]
mode = "auto"
max_window_paragraphs = 1800
overlap_paragraphs = 50
timeout_seconds = 60
min_confidence = "medium"
cache_enabled = true
save_debug_artifacts = true

[structure_validation]
enabled = true
min_paragraphs_for_auto_gate = 40
min_explicit_heading_density = 0.003
max_suspicious_short_body_ratio_without_escalation = 0.05
max_all_caps_or_centered_body_ratio_without_escalation = 0.03
toc_like_sequence_min_length = 4
forbid_heading_only_collapse = true
save_debug_artifacts = true
```

Локальные override можно задавать через `.env`:

```env
DOCX_AI_MODELS_TEXT_DEFAULT=gpt-5.4-mini
DOCX_AI_MODELS_TEXT_OPTIONS=gpt-5.4,gpt-5.4-mini,gpt-5-mini
DOCX_AI_CHUNK_SIZE=6000
DOCX_AI_MAX_RETRIES=3
DOCX_AI_MODELS_STRUCTURE_RECOGNITION_DEFAULT=gpt-5-mini
DOCX_AI_STRUCTURE_RECOGNITION_MODE=auto
DOCX_AI_STRUCTURE_RECOGNITION_MAX_WINDOW_PARAGRAPHS=1800
DOCX_AI_STRUCTURE_RECOGNITION_OVERLAP_PARAGRAPHS=50
DOCX_AI_STRUCTURE_RECOGNITION_TIMEOUT_SECONDS=60
DOCX_AI_STRUCTURE_RECOGNITION_MIN_CONFIDENCE=medium
DOCX_AI_STRUCTURE_RECOGNITION_CACHE_ENABLED=true
DOCX_AI_STRUCTURE_RECOGNITION_SAVE_DEBUG_ARTIFACTS=true
DOCX_AI_STRUCTURE_VALIDATION_ENABLED=true
DOCX_AI_STRUCTURE_VALIDATION_MIN_PARAGRAPHS_FOR_AUTO_GATE=40
DOCX_AI_STRUCTURE_VALIDATION_MIN_EXPLICIT_HEADING_DENSITY=0.003
DOCX_AI_STRUCTURE_VALIDATION_MAX_SUSPICIOUS_SHORT_BODY_RATIO_WITHOUT_ESCALATION=0.05
DOCX_AI_STRUCTURE_VALIDATION_MAX_ALL_CAPS_OR_CENTERED_BODY_RATIO_WITHOUT_ESCALATION=0.03
DOCX_AI_STRUCTURE_VALIDATION_TOC_LIKE_SEQUENCE_MIN_LENGTH=4
DOCX_AI_STRUCTURE_VALIDATION_FORBID_HEADING_ONLY_COLLAPSE=true
DOCX_AI_STRUCTURE_VALIDATION_SAVE_DEBUG_ARTIFACTS=true
DOCX_AI_LOG_LEVEL=INFO
DOCX_AI_IMAGE_MODE_DEFAULT=no_change
DOCX_AI_SEMANTIC_VALIDATION_POLICY=advisory
DOCX_AI_KEEP_ALL_IMAGE_VARIANTS=false
DOCX_AI_MODELS_IMAGE_ANALYSIS_DEFAULT=gpt-5.4-mini
DOCX_AI_MODELS_IMAGE_VALIDATION_DEFAULT=gpt-5.4-mini
DOCX_AI_MODELS_IMAGE_RECONSTRUCTION_DEFAULT=gpt-5.4-mini
DOCX_AI_MODELS_IMAGE_GENERATION_DEFAULT=gpt-image-1.5
DOCX_AI_MODELS_IMAGE_EDIT_DEFAULT=gpt-image-1.5
DOCX_AI_MODELS_IMAGE_GENERATION_VISION_DEFAULT=gpt-5.4-mini
DOCX_AI_ENABLE_VISION_IMAGE_ANALYSIS=true
DOCX_AI_ENABLE_VISION_IMAGE_VALIDATION=true
DOCX_AI_SEMANTIC_REDRAW_MAX_ATTEMPTS=2
DOCX_AI_SEMANTIC_REDRAW_MAX_MODEL_CALLS_PER_IMAGE=9
```

`DOCX_AI_STRUCTURE_RECOGNITION_ENABLED` остаётся только как deprecated compatibility override. Для новых конфигов и automation канонический контракт: `structure_recognition.mode` и `DOCX_AI_STRUCTURE_RECOGNITION_MODE`.

Системный промпт хранится в `prompts/system_prompt.txt`.
Prompt registry для изображений хранится в `prompts/image_prompt_registry.toml`, а profile-файлы — в `prompts/image_profiles/`.

## Логи

Основные runtime-артефакты и логи живут в `.run/`. Эта директория считается production-like local runtime area и подпадает под runtime cleanup/retention. Артефакты под `tests/artifacts/...` относятся к validation/dev workflow и не очищаются runtime retention-механикой.

Проект пишет три основных файла логов:

- `.run/app.log` — лог приложения, обработки блоков и ошибок OpenAI.
- `.run/project.log` — лог PowerShell-скриптов запуска, остановки и status-проверок; теперь это rotating log с ограниченным числом backup-файлов, текущая реализация по умолчанию использует порог `256 KiB` и `5` backup-ов.
- `.run/streamlit.log` — stdout/stderr Streamlit runtime; файл по-прежнему очищается на старте процесса, а во время долгого uptime дополнительно ограничивается WSL control script через периодическую size-check ротацию, текущие дефолты `256 KiB`, `5` backup-ов и проверка каждые `30` секунд, при этом активный путь остаётся `.run/streamlit.log`.

Дополнительно в `.run/` действуют связанные runtime-retention правила:

- `.run/app.log` сохраняет прежнюю ротацию через `RotatingFileHandler`.
- `.run/app.ready` остаётся internal liveness marker для control flow, но steady-state перезаписывается примерно раз в `15` секунд, а не на каждом UI-цикле; содержимое файла не является стабильным внешним data contract.
- `.run/formatting_diagnostics/` теперь имеет централизованную ограниченную retention-политику: хранение до `7` дней, максимум `100` артефактов, pruning по самым старым файлам во время записи.

Если в UI отображается ошибка с `log: ...`, соответствующую техническую запись можно найти по этому идентификатору в `.run/app.log`.

Для временной отладки с повышенной детализацией запускайте приложение с `DOCX_AI_LOG_LEVEL=DEBUG`; после диагностики возвращайте `INFO`, чтобы не раздувать `.run/app.log` без необходимости.

Полный контракт по логированию, таксономия events и правила добавления новых log-event'ов для ИИ-агента зафиксированы в `docs/LOGGING_AND_ARTIFACT_RETENTION.md`. Там же каталогизированы все runtime-артефакты `.run/` и их retention-политики, включая выявленные гэпы (`paragraph_boundary_reports/`, `relation_normalization_reports/`, `paragraph_boundary_ai_review/`, `structure_maps/`, `structure_validation/`).

## Тесты

В проекте есть регрессионные тесты на ключевые контракты:

- конфигурация и env-overrides;
- сборка смысловых блоков и соседнего контекста;
- extraction headings/tables/captions и DOCX semantic hardening;
- retry и обработка ошибок генерации;
- session state и логика статусов;
- одноразовое логирование старта приложения.
- image prompt registry, image validator и placeholder-based image pipeline.

Основной способ запуска тестов:

Через VS Code tasks:

- `Tasks: Run Task -> Run Full Pytest`
- `Tasks: Run Task -> Run Docker CI Parity Pytest`
- `Tasks: Run Task -> Run Current Test File`
- `Tasks: Run Task -> Run Current Test Node`

Через WSL shell:

```bash
bash scripts/test.sh tests/ -q
bash scripts/test.sh tests/test_config.py -vv
bash scripts/test.sh tests/test_config.py::test_name -vv -x
```

## Real Document Validation

Канонический real-document regression target: `tests/sources/Лиетар глава1.docx`.

Канонический registry для universal real-document validation теперь хранится в `corpus_registry.toml`.
Текущий Lietaer harness остаётся штатным entrypoint, но запускается как document profile `lietaer-core` с run profile `ui-parity-default`.
В registry также добавлен второй corpus profile `religion-wealth-core`, привязанный к нормализованному DOCX sibling для `tests/sources/Собственность и богатство в религиях.doc`.
Для stochastic full-tier прогонов доступен soak run profile `ui-parity-soak-3x` с `repeat_count = 3` и aggregate reporting по повторам.

Обычный regression workflow теперь разделён на три tier-а:

- `extraction` — быстрые corpus checks на extractability и coarse structure;
- `structural` — deterministic passthrough через Pandoc + formatting restore без API-вызовов;
- `full` — model-backed UI-parity validation и exceptional quality gate.

Предпочтительный пользовательский путь в VS Code:

- `Tasks: Run Task -> Run Lietaer Real Validation`
- `Tasks: Run Task -> Run Real Document Validation Profile`
- `Tasks: Run Task -> Run Real Document Quality Gate`

Канонический WSL CLI-путь:

```bash
bash scripts/run-real-document-validation.sh
```

Exceptional automated pytest gate:

```bash
bash scripts/run-real-document-quality-gate.sh
```

Не запускайте validator через Windows Python из WSL. Штатный runtime для real-document validation — WSL `.venv` с `PYTHONPATH=.` от корня репозитория.

Каждый прогон теперь пишет run-scoped артефакты в `tests/artifacts/real_document_pipeline/runs/<run_id>/`, а latest aliases обновляет в `tests/artifacts/real_document_pipeline/`.
Latest manifest теперь является стабильным контрактом в течение всего прогона и также фиксирует `document_profile_id`, `run_profile_id`, `validation_tier`, `status`, `acceptance_passed`, run-scoped artifact paths, latest alias paths и явные runtime override-ы относительно UI defaults.

Чтобы не гадать, к какому прогону относятся файлы, используйте manifest:

```text
tests/artifacts/real_document_pipeline/lietaer_validation_latest.json
```

Для live-наблюдения за текущим прогоном используйте progress snapshot:

```text
tests/artifacts/real_document_pipeline/lietaer_validation_progress.json
```

`Run Real Document Quality Gate` запускает только exceptional pytest gate для real-document harness и автоматически валидирует manifest/report. Этот путь намеренно не входит в обычный `Run Full Pytest`.

Подробности workflow и структуры артефактов: `docs/testing/REAL_DOCUMENT_VALIDATION_WORKFLOW.md`.

Низкоуровневый fallback для ручной диагностики:

```bash
source .venv/bin/activate
pytest tests -q
```

Прямой запуск из WSL shell по-прежнему допустим для ручной диагностики:

```bash
bash -lc 'cd /mnt/d/www/projects/2025/DocxAICorrector && . .venv/bin/activate && pytest tests -q'
```

До интерпретации любого test/debug результата сначала проверяйте project runtime в WSL. Вывод случайного системного `python`, `py` или Windows-интерпретатора не считается источником истины, пока не подтверждено поведение проектной `.venv` внутри WSL.

Если нужен живой прогресс по каждому тесту, используйте `pytest tests -vv`.

Для просмотра журнала приложения используйте `Tasks: Run Task -> Tail Streamlit Log` или `./scripts/tail-streamlit-log.ps1`.

Локальная конфигурация pytest хранится в `pyproject.toml`.

## Структура репозитория

```text
.
├── app.py
├── config.py
├── constants.py
├── document.py
├── generation.py
├── logger.py
├── models.py
├── state.py
├── ui.py
├── config.toml
├── requirements.txt
├── prompts/
├── scripts/
├── docs/
├── tests/
└── .github/
```

## Ограничения

- Поддерживаются только inline-изображения в основном потоке документа; floating shapes, SmartArt, OLE и сложная Word-верстка по-прежнему не гарантируются.
- Таблицы и сноски обрабатываются ограниченно.
- Контекст ограничен соседними блоками, а не всей книгой целиком.
- Большие документы обрабатываются заметно дольше.
- `restart_source` используется только как metadata/predicate для stop/failed-сценария; байты поднимаются из `.run/` только при реальном восстановлении файла, чтобы не перечитывать DOCX во время вычисления idle UI-состояния.
- Кеш подготовки документа теперь session-scoped и keyed по lightweight `uploaded_file_token:chunk_size`; он держит не более двух последних документов на сессию вместо process-wide `lru_cache`.
- `completed_source` хранится только для успешного rerun UX, но ограничен по размеру и очищается, как только тот же исходник реально пошёл в новый запуск.

## Разработка

Для локальной работы см. `CONTRIBUTING.md`.
