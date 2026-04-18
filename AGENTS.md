# AGENTS.md

Короткий front-door для ассистентов и automation в этом репозитории.

## Runtime Contract

- Канонический project runtime: WSL project runtime по пути `/mnt/d/www/projects/2025/DocxAICorrector`.
- `.venv` в корне репозитория — это WSL/Linux virtualenv, а не Windows env.
- Для тестов, диагностических импортов, проверки зависимостей и runtime-выводов источником истины считается project runtime внутри WSL.
- Если системный interpreter, Windows `py`/`python` или случайный shell показывают другое состояние, приоритет всегда у project runtime.

## Canonical Test Commands

Используйте только канонический entry point:

```bash
bash scripts/test.sh tests/ -q
bash scripts/test.sh tests/test_file.py -vv
bash scripts/test.sh tests/test_file.py::test_name -vv -x
```

Не запускайте тесты через `py -m pytest`, `python -m pytest` или PowerShell, если явно не подтверждено, что команда выполняется именно внутри project WSL runtime.

Если нужен низкоуровневый fallback, сначала активируйте project env внутри WSL:

```bash
source .venv/bin/activate
pytest tests/ -q
```

## КРИТИЧЕСКИ ВАЖНО: shell identity для Bash tool

Bash tool (инструмент агента) по умолчанию запускает **MSYS/Git Bash**, а **не WSL bash**.

Признаки MSYS shell (не WSL):
- `uname` показывает `MSYS_NT-...` или `MINGW64_NT-...`
- `pwd` возвращает `/d/www/...` (не `/mnt/d/...`)
- `/mnt/d/...` пути не существуют
- `.venv/bin/pytest` не запускается: шебанг `#!/mnt/d/.../python3` сломан в MSYS

Признаки WSL shell:
- `uname` показывает `Linux ...microsoft-standard-WSL2...`
- `/mnt/d/www/...` пути существуют
- `.venv/bin/activate` и `pytest` работают корректно

### Единственный корректный способ запустить тесты из Bash tool

```bash
echo START && wsl.exe -d Debian bash -c "cd /mnt/d/www/projects/2025/DocxAICorrector && . .venv/bin/activate && pytest tests/ -q --tb=short 2>&1" && echo DONE
```

Конкретные варианты:

```bash
# Весь suite
echo START && wsl.exe -d Debian bash -c "cd /mnt/d/www/projects/2025/DocxAICorrector && . .venv/bin/activate && pytest tests/ -q --tb=short 2>&1" && echo DONE

# Один файл
echo START && wsl.exe -d Debian bash -c "cd /mnt/d/www/projects/2025/DocxAICorrector && . .venv/bin/activate && pytest tests/test_file.py -vv --tb=short 2>&1" && echo DONE

# Один тест
echo START && wsl.exe -d Debian bash -c "cd /mnt/d/www/projects/2025/DocxAICorrector && . .venv/bin/activate && pytest tests/test_file.py::test_name -vv -x --tb=short 2>&1" && echo DONE
```

Обязательные правила:
- Всегда `wsl.exe`, не `wsl` (MSYS может не иметь `wsl` в PATH).
- Всегда `echo START && ... && echo DONE` — без этого вывод теряется.
- Всегда `2>&1` — stderr тоже буферизуется отдельно.

`scripts/test.sh` НЕ работает из Bash tool напрямую — скрипт вызывает `exec pytest`, и `pytest` не находится в PATH MSYS окружения.

## Запрещено

- `py -m pytest` из Windows shell.
- Запуск `pytest` через PowerShell bridge / PowerShell wrapper.
- Создание Windows virtualenv в `.venv`.
- Запуск `bash scripts/test.sh ...` или `source .venv/bin/activate && pytest` напрямую из Bash tool без `wsl.exe -d Debian bash -c '...'`.
- Голое `wsl` вместо `wsl.exe` из агентского терминала.
- WSL-команды без echo-маркеров (вывод теряется).

## Надёжный вызов WSL из агентского терминала

Агентский терминал по умолчанию — MSYS/Git Bash или PowerShell, **не WSL**.

### Синтаксис вызова

- Используйте **`wsl.exe`** (не `wsl`) — голое `wsl` может не быть в PATH MSYS.
- Предпочтительная форма: `wsl.exe -d Debian bash -c "..."`.
- `wsl.exe -- bash -lc '...'` тоже работает, но с одинарными кавычками сложнее вкладывать переменные.

### Проблема потери вывода

WSL-команды, запущенные через агентский терминал, часто возвращают пустой вывод. Причина: буферизация stdout при пересечении WSL→MSYS boundary.

Обязательный workaround — обернуть команду echo-маркерами:

```bash
echo START && wsl.exe -d Debian bash -c "cd /mnt/d/www/projects/2025/DocxAICorrector; source .venv/bin/activate; <COMMAND> 2>&1" && echo DONE
```

Без `echo START` в начале агент часто не видит никакого вывода вообще.

### Долгие команды

- Pyright, mypy и другие type-checkers работают 40–120 секунд.
- Используйте `mode=async` и `get_terminal_output` с ожиданием; не считайте пустой вывод признаком зависания.
- При `mode=sync` ставьте `timeout` не менее 180000 мс для type-checking команд.

## Extended Canonical Docs

- `README.md`
- `CONTRIBUTING.md`
- `docs/WORKFLOW_AND_IMAGE_MODES.md`
- `docs/AI_AGENT_DEVELOPMENT_RULES.md`
- `.github/copilot-instructions.md`

## Streamlit Layout Contract

- Для проблем с растянутой шириной, отступами и компоновкой сначала используйте нативные примитивы Streamlit: `st.set_page_config`, `st.columns`, `st.container`, `st.sidebar`, `use_container_width`.
- Если пользователь явно просит без кастомных стилей, не решайте задачу через CSS-селекторы по DOM Streamlit; сначала меняйте layout-композицию штатными средствами Streamlit.
- Для UI/layout-проверки Streamlit используйте встроенный browser-editor/integrated browser как основной способ верификации результата.
- Не прогоняйте полный pytest suite по умолчанию после CSS-only или layout-only правок; для таких изменений сначала достаточно браузерной проверки и точечных тестов только если затронута Python-логика.
