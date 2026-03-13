# Contributing

## Локальная разработка

Проект использует основной Python runtime в WSL. Для штатной разработки, запуска приложения и тестов используйте `.venv/bin/activate` внутри WSL.

1. Создайте виртуальное окружение:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Если нужен отдельный Windows venv для вспомогательных сценариев, его можно поднять отдельно:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
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

Если запуск идёт из Windows shell, используйте WSL-проксирование:

```powershell
wsl.exe -d Debian bash -lc "cd /mnt/d/www/projects/2025/DocxAICorrector && . .venv/bin/activate && streamlit run app.py"
```

## Видимый запуск тестов в VS Code

Во встроенном терминале VS Code:

```bash
bash -lc 'cd /mnt/d/www/projects/2025/DocxAICorrector && . .venv/bin/activate && pytest tests -q'
```

Для живого прогресса по каждому тесту:

```bash
bash -lc 'cd /mnt/d/www/projects/2025/DocxAICorrector && . .venv/bin/activate && pytest tests -vv'
```

Через VS Code Task:

```text
Tasks: Run Task -> Run Full Pytest WSL Visible
```

Task открывает отдельный терминал и оставляет его видимым после завершения.

## Перед pull request

Перед отправкой изменений выполняйте полный прогон в каноническом WSL-окружении:

```bash
source .venv/bin/activate
pytest tests -q
```

Если запуск делается из Windows shell, используйте WSL-проксирование:

```powershell
wsl.exe -d Debian bash -lc "cd /mnt/d/www/projects/2025/DocxAICorrector && . .venv/bin/activate && pytest tests -q"
```

Если нужен именно видимый прогон в UI VS Code, используйте task `Run Full Pytest WSL Visible`.

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