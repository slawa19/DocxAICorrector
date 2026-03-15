# Startup Performance Contract

Этот документ является каноническим source of truth для startup-поведения DocxAICorrector.

Если другой markdown-документ, комментарий в коде или ad-hoc объяснение формулирует startup contract иначе, приоритет всегда у этого файла вместе с `README.md`, `docs/WORKFLOW_AND_IMAGE_MODES.md`, `.github/copilot-instructions.md` и `docs/AI_AGENT_DEVELOPMENT_RULES.md`.

## Цель

Зафиксировать, почему проект загружается быстро сейчас, какие инварианты для этого критичны, какие изменения считаются опасными, и какими тестами нужно страховаться от регрессий.

## Основной принцип

Быстрый старт означает не просто быстрый `health` endpoint, а быстрый first useful render для пользователя.

Следствие:

- server-ready и user-ready считаются разными стадиями;
- всё, что не нужно для первого полезного экрана, не должно блокировать первый render;
- expensive one-time dependencies должны кешироваться на процесс, а не повторяться на каждом rerun.

## Канонические инварианты

### 1. Первый полезный экран раньше фоновой работы

- `app.py` не должен выполнять тяжёлый cleanup, directory scan или иной I/O до первого полезного UI.
- Любой cleanup stale-артефактов должен выполняться вне критического пути старта.
- Для длительной подготовки документа UI обязан показывать live status, а не выглядеть зависшим.

### 2. One-time зависимости не повторяются на каждом rerun

- Конфиг приложения должен кешироваться process-wide.
- System prompt должен читаться из файла один раз на процесс.
- Проверка доступности Pandoc должна выполняться один раз на процесс.
- OpenAI client должен переиспользоваться как singleton в пределах процесса.

### 3. Startup не должен деградировать из-за Streamlit file watching

Для текущего WSL-first workflow на проекте under Windows filesystem обязательны:

- `.streamlit/config.toml`: `fileWatcherType = "none"`
- `.streamlit/config.toml`: `runOnSave = false`

Удаление или изменение этих настроек считается performance-sensitive change.

### 4. WSL-first runtime остаётся обязательным contract

- Единственный штатный runtime для Python, Streamlit, Pandoc и pytest: WSL `.venv`.
- Windows PowerShell допустим только как thin wrapper для lifecycle/diagnostic scripts.
- `.venv-win/` допустим только для editor tooling и статического анализа.

### 5. Readiness-метрики должны быть честными

- `health` endpoint не считается заменой user-visible readiness.
- Любые readiness scripts и diagnostics не должны рапортовать полную готовность раньше, чем UI реально доступен по основному URL.
- Диагностические ready markers допустимы, но они не должны искусственно тормозить обычный lifecycle contract без явной необходимости.

## Запрещённые изменения без явной startup-задачи

- Возвращать синхронный cleanup persisted-source в ранний startup path.
- Убирать кеширование one-time ресурсов ради "простоты".
- Возвращать Streamlit file watching или run-on-save в штатный runtime.
- Переносить runtime проекта с WSL на Windows Python как неявный default.
- Добавлять новый preload, scan, env bootstrap или network bootstrap в начало `app.py`, если он не нужен для первого полезного экрана.

## Обязательные тестовые слои

### Автоматические тесты

Минимально должны существовать и оставаться зелёными следующие проверки:

- structural test на `.streamlit/config.toml`, что `fileWatcherType = "none"` и `runOnSave = false`;
- test на `load_system_prompt()` как lru-cached one-time resource;
- test на `get_client()` как process singleton;
- test на `ensure_pandoc_available()` как cached one-time check;
- UI-level test, что во время активной подготовки рендерится live status, а не пустой экран;
- documentation-contract test, что этот документ упоминается в canonical docs и agent-facing instructions.

### Ручная проверка после performance-sensitive change

После изменений, затрагивающих startup path, нужно отдельно проверить:

- cold start после `Stop Project`;
- повторный warm start;
- first useful render по основному URL;
- отсутствие regressions в `Project Status`, `Start Project`, `Stop Project`.

## Review Checklist

Перед merge startup-sensitive change reviewer должен ответить на вопросы:

1. Появилась ли новая синхронная работа до первого полезного UI?
2. Не исчезло ли одно из one-time cache или singleton-ограничений?
3. Не возвращается ли Streamlit watcher behavior?
4. Не смешивается ли server-ready с user-ready в статусах и диагностике?
5. Обновлены ли docs, если поменялся startup contract?
6. Достаточно ли тестов, чтобы следующая правка не откатила ускорение назад?

## Change-set Contract

Если пользователь явно просит изменить startup contract, ИИ-агент обязан в одном change-set синхронизировать:

- `app.py`
- `config.py`
- `generation.py`
- `.streamlit/config.toml`
- `README.md`
- `CONTRIBUTING.md`
- `docs/WORKFLOW_AND_IMAGE_MODES.md`
- `.github/copilot-instructions.md`
- `docs/AI_AGENT_DEVELOPMENT_RULES.md`
- startup-related tests

Минимальная обязательная проверка после таких изменений:

```bash
bash scripts/test.sh tests/test_startup_performance_contract.py -q
bash scripts/test.sh tests/test_app.py -q
```