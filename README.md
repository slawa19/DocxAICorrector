# DocxAICorrector

DocxAICorrector — это Streamlit-приложение для литературного редактирования `.docx` через OpenAI с промежуточным Markdown и обратной сборкой в `.docx` через Pandoc.

Проект ориентирован на длинные документы, где редактирование по одному абзацу дает слабый результат. Вместо этого приложение собирает смысловые блоки, добавляет соседний контекст только для понимания смысла и возвращает итоговый отредактированный документ.

## Возможности

- Загрузка `.docx` через веб-интерфейс Streamlit.
- Извлечение текста из документа с сохранением ключевой семантики структуры.
- Сборка смысловых блоков вместо наивной обработки по одному абзацу.
- Сохранение заголовков и подзаголовков через style-based, `outlineLvl` и консервативные эвристики.
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
- Обратная сборка Markdown в `.docx` через Pandoc с controlled reference DOCX.
- Пост-нормализация итогового DOCX: heading/body/caption/list/table styling поверх Pandoc output.
- Файловое логирование с `event_id`, контекстом и stack trace.

## Архитектура

После декомпозиции приложение разделено на независимые модули:

```text
app.py         orchestration и main()
constants.py   пути и дефолтные значения
models.py      ParagraphUnit и DocumentBlock
logger.py      логирование и user-facing ошибки
config.py      конфигурация и OpenAI client
document.py    чтение DOCX, ordered block traversal, tables/captions/headings и post-normalization
generation.py  вызовы OpenAI и сборка DOCX через Pandoc/reference-doc
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
```

Единый актуальный source of truth по runtime workflow и image modes лежит в `docs/WORKFLOW_AND_IMAGE_MODES.md`.

Архивный раздел с historical specs, superseded design docs и review snapshots лежит в `docs/ARCHIVE_INDEX.md`.

Исторические документы по decomposition, image mode deep-dives и state/preparation refactor больше не считаются каноническими и читаются только через архивный индекс.

Спецификация hardening-а форматирования DOCX, включая headings, tables, captions и финальную style normalization, лежит в `docs/DOCX_FORMATTING_HARDENING_SPEC_2026-03-13.md`.

## Как работает обработка

Минимальной единицей редактирования является не абзац, а смысловой блок:

- `target_text` — текст, который реально отправляется на редактирование.
- `context_before` — предыдущий соседний контекст только для понимания смысла.
- `context_after` — следующий соседний контекст только для понимания смысла.

Текущие правила сборки блоков:

- заголовок начинает новый блок, рендерится как markdown-heading и приклеивается хотя бы к следующему абзацу;
- последовательные элементы списка группируются вместе;
- таблица является атомарным блоком и не разваливается на обычные абзацы;
- подпись старается оставаться рядом с соседним изображением или таблицей;
- обычные абзацы объединяются до рабочего лимита `chunk_size`;
- слишком длинный абзац не режется внутри себя и уходит отдельным блоком;
- размер соседнего контекста вычисляется автоматически от `chunk_size`.

Это дает модели локальный контекст без потери управляемости: на выходе она должна вернуть только исправленный `target_text`.

На этапе обратной сборки итоговый DOCX проходит два отдельных шага:

- selective restore полезных paragraph-level XML свойств из исходного DOCX;
- semantic normalization итогового документа, чтобы headings, body text, captions, lists, tables и image paragraphs выглядели консистентно, а не как raw Pandoc output.

## Требования

- WSL2 с Linux-дистрибутивом, в котором создаётся и используется текущее `.venv`
- Python 3.11+
- Pandoc
- OpenAI API key
- Windows PowerShell только как thin wrapper для штатных start/stop-скриптов

## Быстрый старт

Проект использует WSL-first workflow. Текущее виртуальное окружение `.venv` является Linux/WSL-окружением, поэтому `pytest`, `streamlit` и проверка зависимостей должны выполняться в WSL. PowerShell-скрипты в `scripts/` являются thin wrapper entry points для штатного запуска в WSL.

Если для вспомогательных Windows-only сценариев нужен отдельный virtualenv, используйте каталог `.venv-win/`. Это окружение допустимо для editor tooling и статического анализа вроде Pyright, но не для runtime wrappers проекта: `scripts/start-project.ps1`, `scripts/stop-project.ps1`, `scripts/status-project.ps1`, `scripts/run-tests.ps1`, `scripts/run-test-file.ps1`, `scripts/run-test-node.ps1` и `scripts/tail-streamlit-log.ps1` по-прежнему обязаны работать через WSL dispatcher. Не создавайте и не активируйте Windows-окружение в `.venv/`: этот путь зарезервирован за WSL-runtime проекта.

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
- `DOCX_AI_DEFAULT_MODEL` — модель редактирования текста по умолчанию.
- `DOCX_AI_MODEL_OPTIONS` — список моделей для sidebar через запятую.
- `DOCX_AI_CHUNK_SIZE` — размер целевого блока документа.
- `DOCX_AI_MAX_RETRIES` — число retry для текстовых вызовов.
- `DOCX_AI_IMAGE_MODE_DEFAULT` — режим изображений по умолчанию: `safe`, `semantic_redraw_direct`, `semantic_redraw_structured`, `compare_all`.
- `DOCX_AI_SEMANTIC_VALIDATION_POLICY` — политика post-check: `advisory` или `strict`.
- `DOCX_AI_KEEP_ALL_IMAGE_VARIANTS` — сохраняет в итоговом DOCX `safe`, `candidate1` и `candidate2` для ручной проверки.
- `DOCX_AI_VALIDATION_MODEL` — модель, используемая validator-веткой.

Пример полного `.env`:

```env
OPENAI_API_KEY=sk-...
DOCX_AI_DEFAULT_MODEL=gpt-5-mini
DOCX_AI_MODEL_OPTIONS=gpt-5.4,gpt-5.4-pro,gpt-5.2,gpt-5.1,gpt-5-mini
DOCX_AI_CHUNK_SIZE=6000
DOCX_AI_MAX_RETRIES=3
DOCX_AI_IMAGE_MODE_DEFAULT=safe
DOCX_AI_SEMANTIC_VALIDATION_POLICY=advisory
DOCX_AI_KEEP_ALL_IMAGE_VARIANTS=false
DOCX_AI_VALIDATION_MODEL=gpt-4.1
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

Базовые значения лежат в `config.toml`:

```toml
default_model = "gpt-5-mini"
model_options = ["gpt-5.4", "gpt-5.4-pro", "gpt-5.2", "gpt-5.1", "gpt-5-mini"]
chunk_size = 6000
max_retries = 3
image_mode_default = "safe"
semantic_validation_policy = "advisory"
keep_all_image_variants = false
validation_model = "gpt-4.1"
enable_vision_image_analysis = true
enable_vision_image_validation = true
semantic_redraw_max_attempts = 2
semantic_redraw_max_model_calls_per_image = 9
```

Локальные override можно задавать через `.env`:

```env
DOCX_AI_DEFAULT_MODEL=gpt-5-mini
DOCX_AI_MODEL_OPTIONS=gpt-5.4,gpt-5.4-pro,gpt-5.2,gpt-5.1,gpt-5-mini
DOCX_AI_CHUNK_SIZE=6000
DOCX_AI_MAX_RETRIES=3
DOCX_AI_IMAGE_MODE_DEFAULT=safe
DOCX_AI_SEMANTIC_VALIDATION_POLICY=advisory
DOCX_AI_KEEP_ALL_IMAGE_VARIANTS=false
DOCX_AI_VALIDATION_MODEL=gpt-4.1
DOCX_AI_ENABLE_VISION_IMAGE_ANALYSIS=true
DOCX_AI_ENABLE_VISION_IMAGE_VALIDATION=true
DOCX_AI_SEMANTIC_REDRAW_MAX_ATTEMPTS=2
DOCX_AI_SEMANTIC_REDRAW_MAX_MODEL_CALLS_PER_IMAGE=9
```

Системный промпт хранится в `prompts/system_prompt.txt`.
Prompt registry для изображений хранится в `prompts/image_prompt_registry.toml`, а profile-файлы — в `prompts/image_profiles/`.

## Логи

Проект пишет два основных файла логов:

- `.run/app.log` — лог приложения, обработки блоков и ошибок OpenAI.
- `.run/project.log` — лог PowerShell-скриптов запуска и остановки.

Если в UI отображается ошибка с `log: ...`, соответствующую техническую запись можно найти по этому идентификатору в `.run/app.log`.

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

- `Tasks: Run Task -> Run Full Pytest WSL`
- `Tasks: Run Task -> Run Current Test File WSL`
- `Tasks: Run Task -> Run Current Test Node WSL`

Через PowerShell wrappers:

```powershell
./scripts/run-tests.ps1
./scripts/run-test-file.ps1 tests/test_config.py
./scripts/run-test-node.ps1 tests/test_config.py::test_name
```

Низкоуровневый fallback для ручной диагностики:

```bash
source .venv/bin/activate
pytest tests -q
```

Прямой запуск из WSL shell по-прежнему допустим для ручной диагностики:

```bash
bash -lc 'cd /mnt/d/www/projects/2025/DocxAICorrector && . .venv/bin/activate && pytest tests -q'
```

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
