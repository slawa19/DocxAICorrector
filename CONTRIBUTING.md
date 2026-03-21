# Contributing

## Локальная разработка

Проект использует основной Python runtime в WSL. Для штатной разработки, запуска приложения и тестов используйте `.venv/bin/activate` внутри WSL.

Startup performance contract считается частью канонической документации. Перед изменениями, затрагивающими старт приложения, сверяйтесь с `docs/STARTUP_PERFORMANCE_CONTRACT.md` и не меняйте startup path без явной задачи на performance или lifecycle.

1. Создайте виртуальное окружение:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Не создавайте Windows virtualenv в `.venv`: это перезапишет WSL-based runtime, на который опираются приложение и штатный тестовый путь.

Если для вспомогательных Windows-only сценариев всё же нужен отдельный venv, используйте другое имя каталога, например `.venv-win`, и не применяйте его для штатного запуска приложения или тестов:

```powershell
python -m venv .venv-win
.\.venv-win\Scripts\Activate.ps1
```

2. Установите зависимости:

```bash
pip install -r requirements.txt
```

3. Установите Pandoc и проверьте `OPENAI_API_KEY` в `.env`.

4. Запустите приложение:

```bash
source .venv/bin/activate
streamlit run app.py
```

Если запуск идёт из Windows shell, используйте штатные wrappers или tasks, а не raw command chains:

```powershell
./scripts/start-project.ps1
```

## Видимый запуск тестов в VS Code

Основной путь через WSL tasks и `scripts/test.sh`:

```text
Tasks: Run Task -> Run Full Pytest
Tasks: Run Task -> Run Current Test File
Tasks: Run Task -> Run Current Test Node
```

Канонический CLI-путь из WSL:

```bash
bash scripts/test.sh tests/ -q
bash scripts/test.sh tests/test_config.py -vv
bash scripts/test.sh tests/test_config.py::test_name -vv -x
```

Низкоуровневый fallback во встроенном WSL-терминале VS Code:

```bash
bash -lc 'cd /mnt/d/www/projects/2025/DocxAICorrector && . .venv/bin/activate && pytest tests -q'
```

Для живого прогресса по каждому тесту:

```bash
bash -lc 'cd /mnt/d/www/projects/2025/DocxAICorrector && . .venv/bin/activate && pytest tests -vv'
```

WSL-driven tasks открывают отдельный терминал и оставляют его видимым после завершения.

## Real Document Validation

Канонический пользовательский путь:

```text
Tasks: Run Task -> Run Lietaer Real Validation
Tasks: Run Task -> Run Real Document Validation Profile
Tasks: Run Task -> Run Real Document Quality Gate
```

Канонический WSL CLI-путь:

```bash
bash scripts/run-real-document-validation.sh
bash scripts/run-real-document-quality-gate.sh
```

Не вызывайте `run_lietaer_validation.py` через Windows Python из WSL и не надейтесь на случайный shell cwd. Используйте только WSL `.venv` и репозиторный root.

Каждый прогон пишет уникальные артефакты в `tests/artifacts/real_document_pipeline/runs/<run_id>/`, обновляет latest manifest в `tests/artifacts/real_document_pipeline/lietaer_validation_latest.json` и live progress snapshot в `tests/artifacts/real_document_pipeline/lietaer_validation_progress.json`.

Для registry-driven запуска произвольного документа используйте `Run Real Document Validation Profile`; canonical Lietaer task остаётся коротким видимым entrypoint для основного regression target.

Exceptional quality gate не входит в обычный полный прогон и должен запускаться только через выделенную task/script. Этот путь сам проверяет latest manifest/report и не требует ручных скриншотов терминала.

Если вы ссылаетесь на real-document прогон в PR или review, указывайте `run_id` и путь к run-specific report.

## Перед pull request

Перед отправкой изменений выполняйте полный прогон через канонический WSL entry point:

```bash
bash scripts/test.sh tests/ -q
```

Низкоуровневый fallback в каноническом WSL-окружении:

```bash
source .venv/bin/activate
pytest tests -q
```

Если правки затрагивают UI или блокировку документа, проверьте также ручной smoke-test на небольшом `.docx`.

Если правки затрагивают test workflow contract, нельзя ограничиваться одной точкой изменений. В одном change-set должны быть синхронизированы:

- `scripts/test.sh`;
- `.vscode/tasks.json` test tasks;
- `tests/test_script_workflow_smoke.py`;
- `README.md`, `CONTRIBUTING.md`, `docs/WORKFLOW_AND_IMAGE_MODES.md`.

Минимальная обязательная проверка после таких правок:

```bash
bash scripts/test.sh tests/test_script_workflow_smoke.py -q
bash scripts/test.sh tests/ -q
```

## Правила изменений

- Держите изменения узкими и без побочных рефакторингов.
- Не меняйте поведение системного промпта без явной задачи на качество модели.
- Для регрессий сначала фиксируйте контракт тестом, затем кодом.
- При изменении структуры модулей синхронизируйте `README.md`, а historical decomposition docs обновляйте только если это действительно нужно для архивного контекста.

## Pull request checklist

- Изменение объяснено в описании PR.
- Тесты проходят локально.
- Документация обновлена, если менялось поведение или структура проекта.
- Лишние временные файлы не попали в коммит.
- Если менялся test workflow contract, синхронно обновлены `scripts/test.sh`, `.vscode/tasks.json`, `tests/test_script_workflow_smoke.py`, `README.md`, `CONTRIBUTING.md`, `docs/WORKFLOW_AND_IMAGE_MODES.md`, а CI остаётся на `bash scripts/test.sh ...`.
- Если менялся startup path, сверена `docs/STARTUP_PERFORMANCE_CONTRACT.md`, обновлены startup-related tests и отдельно проверен first useful render после cold start.
- Для финальной локальной верификации в VS Code использован видимый пользовательский путь запуска тестов, а не hidden terminal capture.