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

## Запрещено

- `py -m pytest` из Windows shell.
- Запуск `pytest` через PowerShell bridge / PowerShell wrapper.
- Создание Windows virtualenv в `.venv`.

## Extended Canonical Docs

- `README.md`
- `CONTRIBUTING.md`
- `docs/WORKFLOW_AND_IMAGE_MODES.md`
- `docs/AI_AGENT_DEVELOPMENT_RULES.md`
- `.github/copilot-instructions.md`
