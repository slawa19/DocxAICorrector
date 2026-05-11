# Copilot CLI Toolkit

Набор PowerShell-скриптов для автономного цикла `KiloCode + Copilot CLI` без VS Code bridge-плагина.

Toolkit решает три задачи:

- находит `copilot.exe` без жесткой привязки к одному пути;
- дает стабильный edit-wrapper для KiloCode orchestration;
- позволяет быстро перенести setup в новый проект.

## Что входит

- `scripts/resolve-copilot-cli.ps1` - находит `copilot.exe` по явному параметру, переменной окружения, `PATH` и известным WinGet/NPM путям.
- `scripts/invoke-copilot.ps1` - универсальный wrapper для non-interactive запуска `copilot -p`.
- `scripts/run-copilot-edit.ps1` - безопасный edit-wrapper для file-edit задач с минимальными permissions по умолчанию.
- `scripts/smoke-copilot-edit.ps1` - локальный smoke-test, который проверяет реальный edit path на временном файле.
- `scripts/install-into-project.ps1` - копирует toolkit и базовую slash-команду в новый проект.

## Пререквизиты

- Windows PowerShell 7+ или совместимый `powershell.exe`.
- Установленный GitHub Copilot CLI.
- Выполненный `copilot login`, если CLI еще не авторизован.
- Для запуска через KiloCode UI - наличие `.kilo/command/copilot-loop.md` в проекте.

Проверка установки:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\copilot-cli\scripts\resolve-copilot-cli.ps1
```

Если все корректно, скрипт вернет абсолютный путь к `copilot.exe`.

## Быстрый старт в этом проекте

Проверить, что CLI находится:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\copilot-cli\scripts\resolve-copilot-cli.ps1
```

Сделать smoke-test edit path:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\copilot-cli\scripts\smoke-copilot-edit.ps1
```

Сделать реальный edit-run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\copilot-cli\scripts\run-copilot-edit.ps1 `
  -WorkingDirectory "D:\www\Projects\2025\DocxAICorrector" `
  -Prompt "Edit only the minimum necessary files to ..."
```

## Безопасность по умолчанию

`run-copilot-edit.ps1` по умолчанию использует:

```text
--allow-tool=write
--no-ask-user
```

Это означает:

- разрешены file edits;
- вопросы пользователю со стороны Copilot CLI отключены;
- shell-команды не разрешены автоматически, пока вы явно их не добавите.

Если нужен `git`-доступ для конкретного сценария:

```powershell
-AllowTool 'shell(git:*)'
```

Если нужна полная автономность с широкими правами, это должно быть осознанным выбором, а не дефолтом.

## Установка в новый проект

Из текущего репозитория:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\copilot-cli\scripts\install-into-project.ps1 `
  -TargetProjectPath "D:\path\to\another-project"
```

Скрипт копирует:

- `tools/copilot-cli/**`
- `.kilo/command/copilot-loop.md`
- `docs/COPILOT_CLI_LOOP_USAGE.md`

Он не перезаписывает существующие файлы без `-Force`.

## Рекомендуемый сценарий использования из KiloCode UI

```text
/copilot-loop
Цель: <что нужно получить>
Контекст: <где смотреть>
Границы: <что нельзя менять>
Проверка: <что запускать или чем мерить готовность>
Автономность: до 3 итераций, не коммить, спрашивай только при важной развилке.
```

## Что toolkit не делает сам

- не коммитит изменения;
- не решает за KiloCode, какие тесты считать достаточными;
- не подменяет canonical verification;
- не хранит историю orchestration loop вместо KiloCode.

Toolkit - это runtime layer. Оркестрация, анализ diff и решение о следующей итерации остаются за KiloCode.

## Примеры

Text-only prompt:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\copilot-cli\scripts\invoke-copilot.ps1 `
  -WorkingDirectory "D:\www\Projects\2025\DocxAICorrector" `
  -Prompt "Reply with exactly: cli-ok"
```

Edit prompt с минимальными правами:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\copilot-cli\scripts\run-copilot-edit.ps1 `
  -WorkingDirectory "D:\www\Projects\2025\DocxAICorrector" `
  -Prompt "Edit only the minimum necessary files to add a focused regression test for ..."
```

Edit prompt с `git`-доступом:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\copilot-cli\scripts\run-copilot-edit.ps1 `
  -WorkingDirectory "D:\www\Projects\2025\DocxAICorrector" `
  -Prompt "Inspect git diff if needed, then make the minimum fix for ..." `
  -AllowTool 'shell(git:*)'
```
