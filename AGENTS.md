# AGENTS.md

Короткий front-door для ассистентов и automation в этом репозитории.

## Где мы сейчас

Прежде чем что-то планировать, прочитайте `docs/WHERE_WE_ARE.md` — это текущая навигация по состоянию
проекта. Источник правды — код и история git; markdown-документы отстают от них.

Не берите направление работ из датированных документов вроде `docs/specs/GLOBAL_PLAN_2026-06-16.md` или
`docs/HANDOFF_2026-07-11.md`: они исторические. Их «следующий шаг» уже сделан (например, UI-слайс —
`specs/013-ui-minimal-screen-and-result/spec.md`, влит в `main`), и повтор такой задачи — потерянное время.

## Spec Kit Contract

Spec Kit is part of the repository workflow, not a local experiment. Commit
`.specify/`, `.agents/skills/speckit-*`, `.claude/commands/speckit-*`, and
generated accepted specs under `specs/`. Keep other future `.agents/` state
ignored unless explicitly reviewed for secrets and team value.

`.specify/memory/constitution.md` is BINDING. Read it before planning any work.
Principles VII (universal rules, no per-book literals) and VIII (evidence must be
fresher than the fix) apply to every change, Spec Kit or not.

Two spec homes, not interchangeable:

- `specs/<NNN>-<slug>/` — one unit of work. Always `spec.md`; `plan.md` and
  `tasks.md` only on full-cycle tier work (see "Which tier" below).
  ALL new specs go here.
- `docs/specs/` — long-lived and historical documents only, including
  `GLOBAL_PLAN_2026-06-16.md` (historical: a log of past decisions, NOT a roadmap —
  do not plan from it) and pre-Spec-Kit forward specs. Create NO new spec here.

Forward planning starts from `docs/WHERE_WE_ARE.md` plus the code and git history, and
lands in a new `specs/<NNN>-<slug>/`. No document in `docs/specs/` is a to-do list.

Every `spec.md` in this repo MUST carry `## Non-goals` and `## Anti-regression` in
addition to Spec Kit's stock sections; see the constitution's Spec Format Contract.
The skills are reachable from Codex as `$speckit-*` and from Claude Code as
`/speckit-*` (thin wrappers in `.claude/commands/`; `.agents/skills/` stays the
single source of truth).

Use Spec Kit when the user asks for:

- a new feature or user-facing workflow;
- behavior with unclear requirements;
- changes to architecture, data contracts, validation pipeline, UI workflow,
  artifact/logging contracts, or real-document processing;
- multi-step implementation where planning and reviewable documentation reduce
  risk.

Do not use Spec Kit for:

- direct requests to run tests, diagnostics, or inspect artifacts;
- tiny bug fixes with obvious expected behavior;
- formatting-only changes;
- isolated test expectation updates;
- real-document failure analysis before the required fresh report checks in the
  Real-document failure analysis contract are complete.

"Use Spec Kit" above means *at least* a `spec.md`. It does NOT mean the full
Spec → Plan → Tasks → Implement cycle; which artifacts a piece of work owes is
decided by the tier below, not by this list.

### Which tier: spec only, or the full cycle

Constitution Principle III defines two tiers and says **the smaller one is the
normal case**. Read it before deciding; the summary here is a routing aid, not
the rule.

- **Spec only — the default.** Defect-driven remediation, review-round
  follow-ups, measurements, negative results and decision records: work whose
  scope is already bounded by the finding that prompted it and whose
  verification is a test run. Write `spec.md`; do not write `plan.md` or
  `tasks.md`. 48 of the repository's 53 specs are this tier.
- **Spec → Plan → Tasks → Implement — the full cycle.** Required when the work
  introduces a new module or a new contract, spans several modules whose order
  of change matters, or has design alternatives worth arguing about before
  anyone writes code. Specs 044-048 are the worked examples.

When the tier is not obvious, **ask the owner**. Guessing "full cycle" is not
the safe default — it spends review budget on paperwork the spec already covers.

**Never write `plan.md` or `tasks.md` after the fact.** If finished work lacks
them, the remedy is a Changelog entry in its `spec.md`, not a reconstructed plan.

> Status: Principle III's two-tier wording is constitution 2.0.0, **ratified by
> the owner on 2026-08-03**. It is binding.
> This section previously demanded `plan.md` unconditionally, which contradicted
> Principle III outright — an agent could satisfy one contract or the other, but
> not both, and chose arbitrarily.

Routing:

1. If no spec exists for the requested feature, read
   `.agents/skills/speckit-specify/SKILL.md` and create `specs/<NNN-name>/spec.md`
   plus its requirements checklist.
2. If the spec has unresolved material ambiguity, read
   `.agents/skills/speckit-clarify/SKILL.md` before planning.
3. If a spec exists, implementation direction is requested **and the work is
   full-cycle tier**, read `.agents/skills/speckit-plan/SKILL.md` and create
   `plan.md`, `research.md`, `data-model.md`, `contracts/` when applicable, and
   `quickstart.md`. On spec-only tier work there is no `plan.md`: implement
   against `spec.md` directly.
4. If a plan exists and execution needs breakdown, read
   `.agents/skills/speckit-tasks/SKILL.md` and create `tasks.md` with small,
   ordered, independently verifiable tasks. No plan means no `tasks.md`.
5. If tasks exist and implementation is requested, read
   `.agents/skills/speckit-implement/SKILL.md` and implement only the selected
   task or the next task batch explicitly requested by the user.

Whenever a Spec Kit plan or task list IS written, it MUST preserve this file's
WSL runtime, canonical verification, real-document evidence, logging/artifact,
and line-ending contracts. Spec-only work carries the same obligation in its
`spec.md`'s `## Non-goals` and `## Anti-regression` sections. Do not silently
replace canonical commands with direct Python/pytest/debug paths.

## Runtime Contract

Канонический project runtime — **WSL Debian** по пути `/mnt/d/www/projects/2025/DocxAICorrector`. Для тестов, диагностических импортов, проверки зависимостей и runtime-выводов источником истины считается он.

### Shell identity: определять фактически, не предполагать

Агентский terminal может оказаться MSYS/Git Bash, PowerShell или уже быть присоединён к WSL. Определите это первой командой (`uname`, `pwd`), а не по предположению.

| Признак | MSYS/Git Bash | WSL |
| --- | --- | --- |
| `uname` | `MSYS_NT-…` / `MINGW64_NT-…` | `Linux …microsoft-standard-WSL2…` |
| `pwd` | `/d/www/…` | `/mnt/d/www/…` |

Проверено 2026-08-03: Bash tool в этом workspace — MINGW64, `pwd` = `/d/www/Projects/2025/DocxAICorrector`.

### Два venv с разными layout'ами

- `.venv/` — **WSL/Linux venv**, layout `bin/`. Единственный с полным набором зависимостей (в т.ч. pdfminer). Канонический.
- `.venv-win/` — **Windows venv**, layout `Scripts/python.exe`, `Scripts/pytest.exe`. Неполный, только debug-only.
- `.venv/Scripts/` **не существует** — не адресуйте Windows-интерпретатор через `.venv`.
- До любого вывода о broken env проверьте фактические executable paths, а не ожидаемый layout. Если фактический layout расходится с контрактом, зафиксируйте это как состояние workspace и выберите рабочий runnable path вместо ложного вывода, что тесты «не запускаются».

### Deterministic readiness check

Перед объявлением canonical tests заблокированными выполните одну локальную проверку без сети:

```bash
wsl.exe -l -q
wsl.exe -d Debian --cd "D:\www\Projects\2025\DocxAICorrector" -- bash -lc "uname; pwd; test -f scripts/test.sh; test -f .venv/bin/activate; echo READY"
```

Если `Debian` виден и READY printed — canonical path доступен: **сразу запускайте requested команду и прекращайте поисковые проверки окружения**. Блокером считается только отсутствие `wsl.exe`, отсутствие `Debian` в списке, отказ `wsl.exe -d Debian` стартовать, отсутствие `scripts/test.sh` или `.venv/bin/activate` внутри Debian. `wsl --list --online` prerequisite не является; его падение ничего не говорит о локальном Debian.

### Транспорт из не-WSL shell

```bash
wsl.exe -d Debian --cd "D:\www\Projects\2025\DocxAICorrector" -- bash scripts/test.sh <selector> [опции]
wsl.exe -d Debian --cd "D:\www\Projects\2025\DocxAICorrector" -- bash -lc "<команда>"
```

- Всегда `wsl.exe`, не голое `wsl` (в PATH MSYS его может не быть).
- Если `uname` уже показывает Linux — **не вкладывайте `wsl.exe` повторно**: это даёт ложные path/stdio проблемы и ломает диагностику.
- Fallback, если `--cd` недоступен: `wsl.exe -d Debian bash -c "cd /mnt/d/www/projects/2025/DocxAICorrector && …"`.

### Прочее по runtime

- Canonical setup нового WSL runtime: `bash scripts/setup-wsl.sh` или task `Setup Project`. Python-зависимости — `requirements.txt`, системные — `system-requirements.apt`.
- PDF import требует LibreOffice (`soffice`/`libreoffice`) внутри WSL (фильтр `--infilter=writer_pdf_import`); не называйте env готовым для PDF без проверки его наличия.
- Structural preparation snapshot: `bash scripts/run-structural-preparation-diagnostic.sh <profile_id> [--run-profile-id <id>]` или task `Run Structural Preparation Diagnostic` — preferred entrypoint поверх ad-hoc `python -c` с JSON-печатью. Для persisted snapshot перенаправляйте stdout в файл (`.run/first20_structural_snapshot.json`), а не в одноразовый one-liner.

## Line Ending Contract

- Репозиторий закрепляет LF как canonical line ending через `.gitattributes` и `.editorconfig`.
- На Windows не считайте CRLF в рабочем дереве допустимой нормой только потому, что shell или editor запущены вне WSL.
- Если после добавления правил старые файлы всё ещё показывают CRLF warnings, это означает, что им нужна разовая renormalization; не интерпретируйте это как отсутствие эффекта от новых настроек.
- После текстовых правок, чувствительных к whitespace/EOL, предпочтительная быстрая проверка: `git diff --check`.

## Canonical vs Debug Path

- **Canonical path** — тот entrypoint, которого требует репозиторный контракт или сам тестовый selector: `scripts/test.sh`, `scripts/run-real-document-validation.sh`, `scripts/run-real-document-quality-gate.sh`, соответствующие VS Code tasks или прямой WSL-run того же shell entrypoint.
- **Debug path** — любой обходной запуск для локальной диагностики: `.venv-win\Scripts\python.exe -m pytest ...`, прямой импорт runner-модуля, узкий internal helper.
- Для `real`, `spec`, `ui-parity`, `validation`, `quality-gate` и shell-script driven сценариев canonical path имеет **абсолютный приоритет**.
- Если requested selector сам завязан на shell-bound contract, debug path не является доказательством его выполнения — он подтверждает только внутреннюю гипотезу.
- **Нельзя подменять canonical path на debug path молча.** Явно маркируйте такой запуск как `debug-only`, если пользователь не просил именно обходной путь.
- Если canonical path недоступен в текущем runtime, сообщите именно это ограничение, а не пишите, что requested test выполнен «эквивалентно другим способом».

## Canonical Test Commands

```bash
bash scripts/test.sh tests/ -q
bash scripts/test.sh tests/test_file.py -vv
bash scripts/test.sh tests/test_file.py::test_name -vv -x
```

Selector идёт **до** опций pytest. Из не-WSL shell — через транспорт `wsl.exe -d Debian --cd ... -- bash scripts/test.sh ...` (см. Runtime Contract).

**`bash scripts/test.sh` из MSYS/Git Bash напрямую запускается, но даёт ложный результат.** Проверено 2026-08-03: подхватывается Windows-интерпретатор `C:\Python312`, прогон падает с `OSError` в `pathlib`. Это не «тесты сломаны», а неверный runtime — всегда идите через `wsl.exe`.

Низкоуровневый fallback — только внутри WSL:

```bash
source .venv/bin/activate && pytest tests/ -q
```

## Финальная верификация и CI

- Для финальной верификации предпочитайте **user-visible task path**, а не agent-side shell capture: `Run Full Pytest`, `Run Current Test File`, `Run Current Test Node`.
- Вывод из agent terminal, даже корректный, не эквивалентен user-visible verification. Shell/Python reruns допустимы для debugging, но финальное утверждение опирается на task path, когда подходящий task существует. Если такого task нет — скажите это прямо, а не подменяйте своим capture.
- **Перед любым «всё зелёное» проверяйте `git status --porcelain`.** Непустой вывод → dirty worktree, и локальный прогон не является доказательством для CI: CI всегда идёт на чистом checkout'е коммита. Особенно затронуты `test_typecheck.py` (pyright), `test_real_document_validation_corpus.py` и любые тесты, зависящие от наличия/отсутствия файлов в `docs/`, `docs/specs/`.
- Для CI-parity сначала подтвердите SHA failing run. Если worktree грязный или ушёл вперёд относительно tested commit — clean worktree или `scripts/docker-ci-parity.sh` прежде чем трактовать результат как репрезентативный.
- Нельзя объявлять GitHub Actions run `passed`/`failed`, пока он не имеет финального `completed` с `conclusion`. Если run ещё `queued`/`in progress` — явно скажите, что итог неизвестен. Web-статус без авторизации (нет logs/annotations) считайте предварительным и подтверждайте локальным canonical прогоном.
- Если web snapshot противоречит прямому подтверждению пользователя (например, email о failed tests) — воспроизведите failing scope локально и явно отметьте расхождение источников.

## Если вывод неполный или прогон долгий

- Частичный или оборванный stdout/stderr трактуйте **сначала как transport/capture problem, а не как тестовый результат**. Не делайте вывод `passed`/`failed` по неполному capture и не пересказывайте его как завершённый прогон.
- Один selector на одну команду; на одно расследование — один активный run, дождитесь его окончания. Не запускайте второй прогон параллельно «чтобы перепроверить ещё раз».
- Если вывод действительно обрывается: **сужайте** до node selector, а не расширяйте до full-suite ради «подтверждения»; при наличии подходящего task используйте его как финальный proof path. Диагностический костыль — обернуть команду `echo START && … && echo DONE` и добавить `2>&1` (stderr буферизуется отдельно).
- Проверено 2026-08-03: потеря вывода на границе WSL→MSYS **не воспроизводится** (800 строк и реальный pytest-прогон проходят целиком без маркеров). Поэтому echo-маркеры — реакция на реальный обрыв, а не обязательный ритуал в каждой команде.
- Type-checkers (pyright) работают 40–120 секунд: используйте async-режим и ожидание, пустой вывод ≠ зависание. При синхронном запуске ставьте timeout ≥ 180000 мс.

## PowerShell: когда допустим

Только для read-only Windows-side диагностики: посчитать метрики по файлам, быстро осмотреть workspace без запуска project runtime, обойти нестабильный capture. **Для тестов, runtime-импортов и любой финальной верификации WSL-first contract не отменяется.**

- Не делайте nested shell chain `cmd.exe -> powershell.exe -> ...`.
- Не передавайте WSL-путь (`/tmp/...`) в `powershell.exe -File` — Windows его не видит. Скрипт создавайте в Windows-доступном пути.
- Запуск: `powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "..."` (execution policy иначе блокирует `.ps1`). Для многострочного кода вынесите его в `.ps1`, а не вкладывайте `$var` и `foreach(...)` в несколько уровней quoting — кавычки ломаются раньше, чем код дойдёт до интерпретатора.
- Не встраивайте сложный PowerShell в `wsl.exe -d Debian bash -lc "..."` и не используйте PowerShell как обходной путь для pytest verification.

## Запрещено

- Запускать `bash scripts/test.sh ...` или `source .venv/bin/activate && pytest` напрямую из Windows/MSYS Bash без `wsl.exe -d Debian ...` transport.
- `py -m pytest` из Windows shell; запуск pytest через PowerShell bridge/wrapper.
- Голое `wsl` вместо `wsl.exe` из агентского терминала.
- Использовать `wsl --list --online` как prerequisite для тестов или как доказательство, что локальный Debian недоступен.
- Заявлять, что тесты «не запускаются» или что env broken, не проверив фактические executable paths.
- Начинать диагностику тестов с Windows Python availability, если задача требует canonical WSL path.
- Подменять shell-bound spec/validation test другим Python runner-ом и описывать это как эквивалент requested test execution.
- Подменять `real`, `spec`, `ui-parity`, `validation`, `quality-gate` сценарий debug path-ом без явной маркировки, что canonical path не выполнялся.
- Интерпретировать неполный stdout как тестовый результат.

## Extended Canonical Docs

- `docs/WHERE_WE_ARE.md`
- `README.md`
- `CONTRIBUTING.md`
- `docs/WORKFLOW_AND_IMAGE_MODES.md`
- `docs/AI_AGENT_DEVELOPMENT_RULES.md`
- `docs/STARTUP_PERFORMANCE_CONTRACT.md`
- `docs/LOGGING_AND_ARTIFACT_RETENTION.md`
- `.github/copilot-instructions.md`

## UI result artifacts

- Не путайте `.run/completed_*` с итоговым результатом обработки: `completed_*` — это persisted cache исходного загруженного файла для restart/reuse после успешного прогона, а не output DOCX.
- Для обычных UI-прогонов итоговые user-visible output artifacts пишутся в `.run/ui_results/` как stem-группа: `.result.md`, `.result.docx` и optional `.result.tts.txt` для audiobook/narration сценариев.
- Канонический лог-сигнал для этих файлов: `ui_result_artifacts_saved`. В его `artifact_paths` лежат точные пути к итоговому Markdown, DOCX и при наличии narration text.
- Для narration-specific анализа используйте `ui_audiobook_artifact_saved`: он указывает точный `tts_text_path`, mode (`standalone` / `postprocess`) и базовые counters (`char_count`, `tag_count`, `excluded_blocks`).
- Если нужно анализировать качество последнего UI-прогона, сначала ищите `ui_result_artifacts_saved` и соответствующие файлы в `.run/ui_results/`, а уже потом fallback'айтесь к промежуточным diagnostics.

## Real-document failure analysis contract

Когда пользователь сообщает, что full-book или другой real-document validation profile (например `lietaer-pdf-full-benchmark`) падает, действует жёсткий контракт анализа. Эти правила нужны, чтобы агент не строил гипотезы по устаревшей памяти и не пропускал блокирующие checks.

Обязательные шаги до любой гипотезы или плана:

1. Прочитать последний run report из `tests/artifacts/real_document_pipeline/<profile>_pdf_full_benchmark_report.json` (генерируемый артефакт) или `tests/artifacts/real_document_pipeline/runs/<latest_run_id>/`.
2. Дословно процитировать массив `failed_checks` и для каждого check записать пару `actual` / `threshold` и overage ratio.
3. При необходимости сверить эти числа с разделом `## 5.0 Live Failure Inventory` в `docs/archive/specs/STRUCTURE_RECOGNITION_COMPLETION_PLAN_2026-05-14.md` — но только как с исторической справкой: документ архивный, его цифры от 2026-05-14, и описанная в нём фича structure-recognition из кода удалена. Расхождение с ним ничего не значит; править архивный документ не нужно. Актуальны только числа из свежего run report.
4. Только после этих трёх шагов формулировать гипотезы.

Запрещено:

- Формировать гипотезы или планы из conversation memory / session summaries без свежей цитаты из run report. Память может быть устаревшей относительно последнего прогона.
- Называть любой check из `failed_checks` "косметикой", "минорной проблемой", "не блокером", "можно отложить" без явного разрешения пользователя проигнорировать его.
- Утверждать, что глава потеряна, фрагмент потерян, или счётчик завышен, без конкретной ссылки `file:line` в актуальном run report или fixture артефакте.
- Предлагать изменения Stage 1 prompt / schema / cache, включая "multi-signal chapter promotion from TOC + body neighborhoods", без отдельной утверждённой спеки под `specs/<NNN>-<slug>/` (все новые спеки живут там, см. раздел Spec Kit Contract). Это вне scope архивных `docs/archive/specs/TOPOLOGY_FIRST_STRUCTURE_RECOVERY_REMEDIATION_SPEC_2026-05-12.md` и `docs/archive/specs/LAYOUT_SIGNAL_EVIDENCE_SLICE_SPEC_2026-05-14.md` (исторические справочники, не место для создания новых спек).
- Предлагать full-book прогон как очередной шаг отладки. Full-book — это milestone, а не tuning loop; правила в Workstream F continuation plan.
- Связывать в один slice независимые failing checks с разными root-cause classes (например bullets + unmapped fragments + index region). Каждый класс — отдельный mini-plan.

Если задача попадает на одну из этих ситуаций, агент должен сначала вернуться к discovery gate в разделе 5.0.1 continuation plan и собрать evidence, и только потом продолжать.

Полный список false directions и условия их отклонения — в разделе `## 11. False Direction Guard` continuation plan.

## Streamlit Layout Contract

- Для проблем с растянутой шириной, отступами и компоновкой сначала используйте нативные примитивы Streamlit: `st.set_page_config`, `st.columns`, `st.container`, `st.sidebar`, `use_container_width`.
- Если пользователь явно просит без кастомных стилей, не решайте задачу через CSS-селекторы по DOM Streamlit; сначала меняйте layout-композицию штатными средствами Streamlit.
- Для UI/layout-проверки Streamlit используйте встроенный browser-editor/integrated browser как основной способ верификации результата.
- Не прогоняйте полный pytest suite по умолчанию после CSS-only или layout-only правок; для таких изменений сначала достаточно браузерной проверки и точечных тестов только если затронута Python-логика.
