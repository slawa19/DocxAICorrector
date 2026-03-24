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
wsl -- bash -lc 'cd /mnt/d/www/projects/2025/DocxAICorrector && . .venv/bin/activate && pytest tests/ -q --tb=short'
```

Конкретные варианты:

```bash
# Весь suite
wsl -- bash -lc 'cd /mnt/d/www/projects/2025/DocxAICorrector && . .venv/bin/activate && pytest tests/ -q --tb=short'

# Один файл
wsl -- bash -lc 'cd /mnt/d/www/projects/2025/DocxAICorrector && . .venv/bin/activate && pytest tests/test_file.py -vv --tb=short'

# Один тест
wsl -- bash -lc 'cd /mnt/d/www/projects/2025/DocxAICorrector && . .venv/bin/activate && pytest tests/test_file.py::test_name -vv -x --tb=short'
```

`scripts/test.sh` НЕ работает из Bash tool напрямую — скрипт вызывает `exec pytest`, и `pytest` не находится в PATH MSYS окружения.

## Запрещено

- `py -m pytest` из Windows shell.
- Запуск `pytest` через PowerShell bridge / PowerShell wrapper.
- Создание Windows virtualenv в `.venv`.
- Запуск `bash scripts/test.sh ...` или `source .venv/bin/activate && pytest` напрямую из Bash tool без `wsl -- bash -lc '...'`.

## Extended Canonical Docs

- `README.md`
- `CONTRIBUTING.md`
- `docs/WORKFLOW_AND_IMAGE_MODES.md`
- `docs/AI_AGENT_DEVELOPMENT_RULES.md`
- `.github/copilot-instructions.md`
