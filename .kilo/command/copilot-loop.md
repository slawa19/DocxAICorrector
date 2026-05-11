---
description: Run an autonomous KiloCode + Copilot CLI edit loop
---
Run an autonomous development loop using Copilot CLI as an external edit engine and KiloCode as the orchestrator.

User task:

```text
$ARGUMENTS
```

Protocol:

1. Interpret the user task as the goal for KiloCode, not as a raw Copilot CLI prompt.
2. Inspect the relevant code/specs first. Prefer `Glob`, `Grep`, and `Read`; use subagents for focused exploration if useful.
3. Break the work into at most 3 narrow iterations. This is a hard cap, not a target.
4. For each iteration, call Copilot CLI with a scoped edit prompt. Keep permissions minimal: allow file writes, and do not use `--allow-all-tools` unless the user explicitly requested full autopilot.
5. After Copilot CLI returns, inspect `git status` and `git diff`. Treat the diff as the source of truth, not Copilot CLI's text summary.
6. Run only relevant targeted checks. In this repository, follow `AGENTS.md`: use canonical WSL/test entrypoints when claiming verification, and clearly label debug-only checks.
7. If the diff or checks show obvious fixable issues, run another iteration or fix small issues directly.
8. Stop immediately after successful completion. Use a second or third iteration only if the previous iteration's diff, checks, or unresolved scope show that more work is actually needed. Never continue just to consume the iteration budget.

Copilot CLI runtime toolkit:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\copilot-cli\scripts\run-copilot-edit.ps1 `
  -WorkingDirectory "<REPO_PATH>" `
  -Prompt "<ITERATION_PROMPT>"
```

Resolve Copilot CLI path when needed:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\copilot-cli\scripts\resolve-copilot-cli.ps1
```

Iteration prompt contract for Copilot CLI:

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

Stop rules:

- Stop and ask the user if there are multiple architectural paths with meaningful tradeoffs.
- Stop if changes would delete or rewrite large areas outside the requested scope.
- Stop if the work conflicts with unrelated user changes in the same files.
- Stop if secrets, credentials, external access, or manual setup is required.
- Stop if verification is ambiguous or canonical verification is unavailable for a shell-bound scenario.
- Stop when the task is complete and another iteration would only add noise.

Final response contract:

```text
Результат
- Выполнено: <1-4 bullets>
- Изменены файлы: <paths>
- Проверки: <commands and outcomes>
- Итерации: <N of max 3>
- Ограничения/риски: <if any>

Продолжение
<self-contained prompt for continuing in this or another KiloCode session, only if work remains or a handoff is useful>
```

If the task is fully complete and no handoff is needed, state that no continuation prompt is required.
If a continuation prompt is included, it must be self-contained: include current status, changed files, checks run, remaining work, constraints, and the next narrow objective.
