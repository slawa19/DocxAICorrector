# Contributing

## Локальная разработка

Проект использует основной Python runtime в WSL. Для штатной разработки, запуска приложения и тестов используйте `.venv/bin/activate` внутри WSL.

1. Создайте виртуальное окружение:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Не создавайте Windows virtualenv в `.venv`: это перезапишет WSL-based runtime, на который опираются приложение, wrappers и tests.

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

Основной путь через wrappers и tasks:

```text
Tasks: Run Task -> Run Full Pytest WSL
Tasks: Run Task -> Run Current Test File WSL
Tasks: Run Task -> Run Current Test Node WSL
```

Из PowerShell:

```powershell
./scripts/run-tests.ps1
./scripts/run-test-file.ps1 tests/test_config.py
./scripts/run-test-node.ps1 tests/test_config.py::test_name
```

Низкоуровневый fallback во встроенном WSL-терминале VS Code:

```bash
bash -lc 'cd /mnt/d/www/projects/2025/DocxAICorrector && . .venv/bin/activate && pytest tests -q'
```

Для живого прогресса по каждому тесту:

```bash
bash -lc 'cd /mnt/d/www/projects/2025/DocxAICorrector && . .venv/bin/activate && pytest tests -vv'
```

Wrapper-driven tasks открывают отдельный терминал и оставляют его видимым после завершения.

## Перед pull request

Перед отправкой изменений выполняйте полный прогон через штатный wrapper:

```powershell
./scripts/run-tests.ps1
```

Низкоуровневый fallback в каноническом WSL-окружении:

```bash
source .venv/bin/activate
pytest tests -q
```

Если правки затрагивают UI или блокировку документа, проверьте также ручной smoke-test на небольшом `.docx`.

## Правила изменений

- Держите изменения узкими и без побочных рефакторингов.
- Не меняйте поведение системного промпта без явной задачи на качество модели.
- Для регрессий сначала фиксируйте контракт тестом, затем кодом.
- При изменении структуры модулей синхронизируйте `README.md` и `docs/decomposition.md`.

## Pull request checklist

- Изменение объяснено в описании PR.
- Тесты проходят локально.
- Документация обновлена, если менялось поведение или структура проекта.
- Лишние временные файлы не попали в коммит.