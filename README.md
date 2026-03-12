# DocxAICorrector

DocxAICorrector — это Streamlit-приложение для литературного редактирования `.docx` через OpenAI с промежуточным Markdown и обратной сборкой в `.docx` через Pandoc.

Проект ориентирован на длинные документы, где редактирование по одному абзацу дает слабый результат. Вместо этого приложение собирает смысловые блоки, добавляет соседний контекст только для понимания смысла и возвращает итоговый отредактированный документ.

## Возможности

- Загрузка `.docx` через веб-интерфейс Streamlit.
- Извлечение текста из документа с базовыми структурными эвристиками.
- Сборка смысловых блоков вместо наивной обработки по одному абзацу.
- Сохранение локального контекста через `context_before` и `context_after`.
- Последовательная обработка блоков через OpenAI Responses API.
- Retry для временных API-сбоев.
- Живой статус обработки, журнал по блокам и activity feed в UI.
- Сохранение промежуточного Markdown при частичном сбое.
- Placeholder-based pipeline для inline-изображений в `.docx`.
- Safe-mode для изображений и semantic-redraw ветка с обязательным Level 1 post-check.
- Compare-all режим: генерация safe, creative и conservative вариантов изображения с немедленной вставкой всех вариантов в итоговый DOCX.
- Обратная сборка Markdown в `.docx` через Pandoc.
- Файловое логирование с `event_id`, контекстом и stack trace.

## Архитектура

После декомпозиции приложение разделено на независимые модули:

```text
app.py         orchestration и main()
constants.py   пути и дефолтные значения
models.py      ParagraphUnit и DocumentBlock
logger.py      логирование и user-facing ошибки
config.py      конфигурация и OpenAI client
document.py    чтение DOCX и сборка блоков
generation.py  вызовы OpenAI и сборка DOCX через Pandoc
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

Детальная спецификация декомпозиции лежит в `docs/decomposition.md`.

Описание режимов обработки изображений в UI, включая compare-all, лежит в `docs/IMAGE_UI_PIPELINE_MODES.md`.

Спецификация state-machine и кеша подготовки документа лежит в `docs/REFACTORING_STATE_AND_PREPARATION_SPEC.md`.

## Как работает обработка

Минимальной единицей редактирования является не абзац, а смысловой блок:

- `target_text` — текст, который реально отправляется на редактирование.
- `context_before` — предыдущий соседний контекст только для понимания смысла.
- `context_after` — следующий соседний контекст только для понимания смысла.

Текущие правила сборки блоков:

- заголовок начинает новый блок и приклеивается хотя бы к следующему абзацу;
- последовательные элементы списка группируются вместе;
- обычные абзацы объединяются до рабочего лимита `chunk_size`;
- слишком длинный абзац не режется внутри себя и уходит отдельным блоком;
- размер соседнего контекста вычисляется автоматически от `chunk_size`.

Это дает модели локальный контекст без потери управляемости: на выходе она должна вернуть только исправленный `target_text`.

## Требования

- WSL2 с Linux-дистрибутивом, в котором создаётся и используется текущее `.venv`
- Python 3.11+
- Pandoc
- OpenAI API key
- Windows PowerShell только как thin wrapper для штатных start/stop-скриптов

## Быстрый старт

Проект использует WSL-first workflow. Текущее виртуальное окружение `.venv` является Linux/WSL-окружением, поэтому `pytest`, `streamlit` и проверка зависимостей должны выполняться в WSL. PowerShell-скрипты в `scripts/` только проксируют запуск в WSL.

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
- `DOCX_AI_ENABLE_POST_REDRAW_VALIDATION` — включает Level 1 post-check для AI-перерисовки.
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
DOCX_AI_ENABLE_POST_REDRAW_VALIDATION=true
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
enable_post_redraw_validation = true
validation_model = "gpt-4.1"
enable_vision_image_analysis = true
enable_vision_image_validation = true
semantic_redraw_max_attempts = 3
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
DOCX_AI_ENABLE_POST_REDRAW_VALIDATION=true
DOCX_AI_VALIDATION_MODEL=gpt-4.1
DOCX_AI_ENABLE_VISION_IMAGE_ANALYSIS=true
DOCX_AI_ENABLE_VISION_IMAGE_VALIDATION=true
DOCX_AI_SEMANTIC_REDRAW_MAX_ATTEMPTS=3
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
- retry и обработка ошибок генерации;
- session state и логика статусов;
- одноразовое логирование старта приложения.
- image prompt registry, image validator и placeholder-based image pipeline.

Запуск:

```bash
source .venv/bin/activate
pytest tests -q
```

Если нужен запуск именно из PowerShell, используйте проксирование в WSL:

```powershell
wsl.exe -d Debian bash -lc "cd /mnt/d/www/projects/2025/DocxAICorrector && . .venv/bin/activate && pytest tests -q"
```

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
