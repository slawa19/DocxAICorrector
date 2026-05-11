# Спецификация: автономный цикл KiloCode + Copilot CLI

Дата: 2026-05-11
Статус: черновик для внедрения
Цель: заменить VS Code bridge-плагин простым циклом, где KiloCode оркестрирует задачу, а Copilot CLI используется как внешний edit engine.

## 1. Решение

Основная архитектура:

```text
KiloCode UI -> /copilot-loop -> Copilot CLI -> git diff -> targeted checks -> KiloCode decision
```

Роли:

- KiloCode остается главным оркестратором, ревьюером и контроллером остановки.
- Copilot CLI получает узкие edit prompts и может менять файлы.
- `git diff` является источником истины о результате каждой итерации.
- Тесты, typecheck и диагностические команды запускаются KiloCode после правок, а не доверяются текстовому отчету Copilot CLI.

Плагин `Copilot Orchestrator Bridge` не используется для разработки. Он умеет только `prompt file -> vscode.lm -> response file` и не является editing runtime.

## 2. Цели

- Запускать задачу из KiloCode UI одной командой.
- Делать 2-3 итерации без участия пользователя.
- Минимизировать копипасту между сессиями.
- Останавливаться только на важных развилках, рисках или завершении.
- Возвращать понятный результат: что сделано, что проверено, какие файлы изменены, как продолжить.

## 3. Non-goals

- Не строить новый VS Code extension.
- Не использовать `vscode.lm` как основной runtime для правок.
- Не давать Copilot CLI `--allow-all-tools` по умолчанию.
- Не коммитить изменения автоматически.
- Не запускать полный test suite по умолчанию, если достаточно узких проверок.
- Не скрывать неоднозначные решения под видом автономности.

## 4. Loop protocol

Каждый запуск `/copilot-loop` выполняется как ограниченный цикл:

```text
max_iterations = 3

for iteration in 1..max_iterations:
  1. KiloCode формирует scoped prompt для Copilot CLI.
  2. Copilot CLI вносит минимальные изменения.
  3. KiloCode проверяет git status и git diff.
  4. KiloCode запускает релевантные узкие проверки.
  5. KiloCode решает:
     - завершить задачу;
     - сделать следующую итерацию;
     - остановиться и запросить решение пользователя.
```

`max_iterations` - это верхняя граница safety budget, а не цель обязательно сделать несколько шагов. Если задача корректно завершена после первой итерации, цикл должен остановиться сразу.

Каждая итерация должна иметь короткую цель. Если задача большая, KiloCode сначала дробит ее на безопасные этапы и передает Copilot CLI только текущий этап.

## 5. Stop rules

KiloCode останавливает цикл до исчерпания лимита, если возникает одно из условий:

- требуется архитектурный выбор с несколькими жизнеспособными вариантами;
- изменения затрагивают файлы с явными чужими незавершенными правками;
- Copilot CLI предлагает удалить или массово переписать существенную часть проекта;
- нужны секреты, доступы, внешние credentials или ручная настройка;
- проверки дают неоднозначный результат;
- canonical verification недоступна, а debug-only path недостаточен для вывода;
- задача выполнена и дальнейшая итерация будет только шумом.

## 6. Copilot CLI invocation policy

Базовый режим:

```powershell
& "C:\Users\slawa\AppData\Local\Microsoft\WinGet\Packages\GitHub.Copilot_Microsoft.Winget.Source_8wekyb3d8bbwe\copilot.exe" `
  -C "D:\www\Projects\2025\DocxAICorrector" `
  -p "<ITERATION_PROMPT>" `
  -s `
  --allow-tool=write `
  --no-ask-user
```

Дополнительные shell permissions выдаются только точечно. Рекомендуемый максимум для обычной итерации:

```powershell
--allow-tool=write
--allow-tool='shell(git:*)'
```

По умолчанию запрещено:

```powershell
--allow-all-tools
```

Если нужны тесты, KiloCode запускает их сам после завершения Copilot CLI. Для этого репозитория KiloCode должен соблюдать `AGENTS.md` и использовать canonical WSL/test entrypoints, когда результат заявляется как proof.

## 7. Prompt contract for Copilot CLI

Каждый prompt к Copilot CLI должен содержать:

- конкретную цель одной итерации;
- список файлов или областей, если они известны;
- ограничение на минимальный diff;
- запрет на commit/push;
- запрет на unrelated refactoring;
- требование остановиться после file edits;
- ожидаемый формат краткого отчета.

Шаблон:

```text
You are an edit engine called by KiloCode.

Task for this iteration:
<specific narrow task>

Constraints:
- Modify only files needed for this iteration.
- Keep the diff minimal.
- Do not commit, push, install dependencies, or perform broad refactoring.
- Do not change unrelated behavior.
- If the task is ambiguous, make the smallest safe change and report the ambiguity.

After editing, return:
- files changed;
- short rationale;
- any follow-up needed.
```

## 8. User task contract

Пользователь формулирует задачу не как техническую инструкцию для Copilot CLI, а как цель для KiloCode-оркестратора.

Хороший формат:

```text
/copilot-loop
Цель: <какое поведение нужно получить>
Контекст: <где это видно или почему нужно>
Границы: <что нельзя трогать>
Проверка: <как понять, что готово>
Автономность: сделай до 3 итераций, спрашивай только при важной развилке.
```

Минимальный формат:

```text
/copilot-loop <цель задачи>. Сделай до 3 итераций автономно, не коммить, остановись только при важной развилке или завершении.
```

Плохой формат:

```text
Сделай лучше весь модуль.
```

Причина: слишком широкий scope, невозможно определить успешное завершение и безопасный diff.

## 9. Result contract

В конце KiloCode возвращает человеку один читаемый отчет:

```text
Результат
- Выполнено: <1-4 пункта>
- Изменены файлы: <пути>
- Проверки: <commands and results>
- Итерации: <N из max 3>
- Ограничения/риски: <если есть>

Продолжение
<готовый prompt, который можно вставить в эту или новую KiloCode-сессию>
```

Блок `Продолжение` не означает, что следующая итерация обязательна. Он нужен только если работа реально не завершена или если полезно передать состояние в новую сессию без пересказа.

Если продолжение не нужно, KiloCode должен явно написать, что задача завершена и дополнительный continuation prompt не требуется.

Если блок `Продолжение` присутствует, он должен быть самодостаточным: включать текущий статус, оставшуюся цель, важные ограничения и точку входа. Пользователь не должен пересказывать историю руками.

## 10. Continuation prompt template

```text
Продолжи работу по задаче после предыдущего /copilot-loop.

Текущий статус:
- Сделано: <summary>
- Изменены файлы: <files>
- Проверки: <checks>
- Осталось: <remaining work>

Ограничения:
- Не коммить.
- Сохранять минимальный diff.
- Не трогать unrelated files.
- Сделать максимум 2 дополнительные итерации.
- Остановиться при архитектурной развилке или если проверки неоднозначны.

Следующая цель:
<next narrow objective>
```

## 11. Implementation deliverables

Минимальный набор:

- `.kilo/command/copilot-loop.md` - KiloCode slash command с protocol и stop rules.
- `docs/COPILOT_CLI_LOOP_USAGE.md` - короткая инструкция для пользователя.
- Эта спецификация - источник требований к поведению loop.

Опционально позже:

- `tools/copilot-cli/run-copilot-edit.ps1` - wrapper над конкретным путем `copilot.exe`.
- `.run/copilot-cli-loop/last-result.md` - machine-readable/latest human-readable summary.
- `.run/copilot-cli-loop/continuation-prompt.md` - автоматически обновляемый prompt продолжения.

## 12. Acceptance criteria

- Пользователь может запустить задачу из KiloCode UI одной slash-командой.
- KiloCode может сделать 2-3 итерации без ручного вмешательства.
- После каждой итерации KiloCode проверяет diff, а не доверяет только словам Copilot CLI.
- Финальный ответ содержит понятный результат и готовый prompt продолжения.
- Bridge-плагин не участвует в основном development path.
