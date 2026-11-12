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
  `tasks.md`. The overwhelming majority of specs are this tier — do not quote a
  number from memory, count it:

  ```bash
  ls -d specs/*/ | wc -l          # all specs
  ls specs/*/plan.md | wc -l      # full-cycle tier (the only ones that owe plan.md)
  ```

  On 2026-08-07 that was 58 and 5, i.e. 53 spec-only. The constitution's "48 of 53"
  (`.specify/memory/constitution.md:105-106`) is the count as it stood at
  ratification on 2026-08-03, not a live figure.
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

Канонический project runtime — **WSL Debian** по пути `/mnt/d/Work/Projects/DocxAICorrector` (Windows: `D:\Work\Projects\DocxAICorrector`). Для тестов, диагностических импортов, проверки зависимостей и runtime-выводов источником истины считается он.

С 2026-09-20 чекаут живёт здесь; прежний путь `D:\www\Projects\2025\DocxAICorrector`
(`/mnt/d/www/projects/2025/DocxAICorrector`) на диске больше не существует, и команда с ним падает
на `--cd`, а не на тестах. Датированные записи со старым путём в спеках и журналах остаются
историей и не правятся.

**Что не переезжает вместе с чекаутом.** `.env` (ключи API), `tests/artifacts/real_document_pipeline/runs/<run_id>/`
(отчёты прогонов) и `.run/` исключены из git и живут только в том каталоге, где их создали. После
переноса или нового clone их надо восстановить вручную; иначе «ключа нет» и «прогонов нет» — это
состояние нового чекаута, а не дефект кода (так и было найдено 2026-11-07).

### Shell identity: определять фактически, не предполагать

Агентский terminal может оказаться MSYS/Git Bash, PowerShell или уже быть присоединён к WSL. Определите это первой командой (`uname`, `pwd`), а не по предположению.

| Признак | MSYS/Git Bash | WSL |
| --- | --- | --- |
| `uname` | `MSYS_NT-…` / `MINGW64_NT-…` | `Linux …microsoft-standard-WSL2…` |
| `pwd` | `/d/Work/…` | `/mnt/d/Work/…` |

Проверено 2026-08-03 по старому пути: Bash tool в этом workspace — MINGW64, `pwd` =
`/d/www/Projects/2025/DocxAICorrector`. С 2026-09-20 чекаут живёт в `D:\Work\Projects\DocxAICorrector`,
и тот же признак выглядит как `pwd` = `/d/Work/Projects/DocxAICorrector` (`uname` 2026-11-07 —
по-прежнему `MINGW64_NT`). Правило не изменилось: shell определяется по `uname`, а не по пути.

### Два venv с разными layout'ами

- `.venv/` — **WSL/Linux venv**, layout `bin/`. Единственный с полным набором зависимостей (в т.ч. pdfminer). Канонический.
- `.venv-win/` — **Windows venv**, layout `Scripts/python.exe`, `Scripts/pytest.exe`. Неполный, только debug-only.
- `.venv/Scripts/` **не существует** — не адресуйте Windows-интерпретатор через `.venv`.
- До любого вывода о broken env проверьте фактические executable paths, а не ожидаемый layout. Если фактический layout расходится с контрактом, зафиксируйте это как состояние workspace и выберите рабочий runnable path вместо ложного вывода, что тесты «не запускаются».

### Deterministic readiness check

Перед объявлением canonical tests заблокированными выполните одну локальную проверку без сети:

```bash
wsl.exe -l -q
wsl.exe -d Debian --cd "D:\Work\Projects\DocxAICorrector" -- bash -lc "uname; pwd; test -f scripts/test.sh; test -f .venv/bin/activate; echo READY"
```

Если `Debian` виден и READY printed — canonical path доступен: **сразу запускайте requested команду и прекращайте поисковые проверки окружения**. Блокером считается только отсутствие `wsl.exe`, отсутствие `Debian` в списке, отказ `wsl.exe -d Debian` стартовать, отсутствие `scripts/test.sh` или `.venv/bin/activate` внутри Debian. `wsl --list --online` prerequisite не является; его падение ничего не говорит о локальном Debian.

### Транспорт из не-WSL shell

```bash
wsl.exe -d Debian --cd "D:\Work\Projects\DocxAICorrector" -- bash scripts/test.sh <selector> [опции]
wsl.exe -d Debian --cd "D:\Work\Projects\DocxAICorrector" -- bash -lc "<команда>"
```

- Всегда `wsl.exe`, не голое `wsl` (в PATH MSYS его может не быть).
- Если `uname` уже показывает Linux — **не вкладывайте `wsl.exe` повторно**: это даёт ложные path/stdio проблемы и ломает диагностику.
- Fallback, если `--cd` недоступен: `wsl.exe -d Debian bash -c "cd /mnt/d/Work/Projects/DocxAICorrector && …"`.

### Боковые worktree для агентов

Механика выстрадана 2026-08-07/08, когда над деревом одновременно работали несколько агентов. Каждый
пункт стоил либо потерянного прогона, либо красного CI.

- **Worktree создавайте ВНЕ репозитория** (например `D:\Temp\claude\wt-<slug>`, он же
  `/mnt/d/Temp/claude/wt-<slug>`; до 2026-11-07 здесь стоял `E:\Temp\claude`, но диска `E:` на этой
  машине нет). Встроенная изоляция агентского инструмента кладёт worktree внутрь
  дерева, и git отказывается: `core.worktree redirect`. `.venv` подключайте симлинком на главное
  дерево — без него `scripts/test.sh` не найдёт активатор и агент объявит окружение сломанным.
- **`$VAR` схлопывается в пустую строку** на границе Git Bash → `wsl.exe`, ДАЖЕ в одинарных кавычках.
  В таких командах — только литеральные пути и никаких циклов `for`: подстановка должна произойти до
  передачи, а не после.
- **В боковом worktree `git` под WSL не работает.** `.git` там — файл с записью `gitdir:` по
  windows-пути, который WSL резолвит относительно текущего каталога и отвечает «not a git repository».
  Поэтому **тесты, читающие историю, проверяются только в главном дереве**. С 2026-08-08 в боковом они
  не падают, а пропускаются с объяснением (`tests/test_spec_status_consistency.py`): красные тесты,
  которые ничего не значат, приучают не смотреть на красное.
- **Голое `python` в Git Bash из бокового worktree разрешается в `.venv-win` ГЛАВНОГО дерева** — агент
  незаметно лезет в чужое дерево и мерит не то, что думает. Идите через
  `wsl.exe -d Debian -- bash -lc '... python3 ...'`.
- **Мутационная проверка — это запись.** Разводить по деревьям надо всех, кто МУТИРУЕТ, а не только
  тех, кто коммитит: 2026-08-08 три ревьюера в общем дереве перебили измерения друг другу, и один снёс
  мутацию второго в середине его прогона.

### Прочее по runtime

- Canonical setup нового WSL runtime: `bash scripts/setup-wsl.sh` или task `Setup Project`. Python-зависимости — `requirements.txt`, системные — `system-requirements.apt`.
- PDF импортируется по текстовому слою через pdfminer (`src/docxaicorrector/processing/processing_runtime.py`, `_convert_pdf_text_layer_to_docx`),
  OCR — по `DOCXAI_PDF_OCR_IMPORT_ENABLED` (нужны `ocrmypdf` и Tesseract). LibreOffice (`soffice`) внутри WSL нужен для
  старого `.doc` и для PDF текста озвучки; не называйте env готовым для них без проверки его наличия. До 2026-11-12 здесь
  стояло «PDF import требует LibreOffice (`--infilter=writer_pdf_import`)»: функция `_convert_pdf_to_docx` осталась в коде, но
  не вызывается.
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
- **Перенос ветки на свежий `main` требует ПОВТОРНОГО полного прогона в главном дереве.** Зелень «у
  себя» после переноса не значит ничего: 2026-08-08 дважды за день ветка была зелёной до переноса и
  падала после, потому что параллельная работа удалила символ, который патчили её новые тесты
  (`app.push_activity` — `AttributeError` прямо на строке патча). **Ни диф, ни сверка чисел этого не
  ловят:** перенос шёл без конфликтов, а арифметика сходилась — 2575 passed + 6 failed против 2575 в
  `main` плюс шесть тестов ветки. Ловит только прогон.
- **Не называйте номер спеки в ТЕМЕ коммита, если коммит не является работой по ней.** Гард
  `tests/test_spec_status_consistency.py` читает тему и засчитывает номер как заявку на работу; если
  статус той спеки честно говорит «не начато», CI падает. Проверено на себе дважды 2026-08-08 —
  оба раза на коммите, чьё ТЕЛО связь как раз отрицало (отрицание матчер прочитать не может, поэтому
  тело он больше не читает). Контекст называйте в теле; тема несёт отнесение.

## Если вывод неполный или прогон долгий

- Частичный или оборванный stdout/stderr трактуйте **сначала как transport/capture problem, а не как тестовый результат**. Не делайте вывод `passed`/`failed` по неполному capture и не пересказывайте его как завершённый прогон.
- Один selector на одну команду; на одно расследование — один активный run, дождитесь его окончания. Не запускайте второй прогон параллельно «чтобы перепроверить ещё раз».
- Если вывод действительно обрывается: **сужайте** до node selector, а не расширяйте до full-suite ради «подтверждения»; при наличии подходящего task используйте его как финальный proof path. Диагностический костыль — обернуть команду `echo START && … && echo DONE` и добавить `2>&1` (stderr буферизуется отдельно).
- Проверено 2026-08-03: потеря вывода на границе WSL→MSYS **не воспроизводится** (800 строк и реальный pytest-прогон проходят целиком без маркеров). Поэтому echo-маркеры — реакция на реальный обрыв, а не обязательный ритуал в каждой команде.
- Type-checkers (pyright) работают 40–120 секунд: используйте async-режим и ожидание, пустой вывод ≠ зависание. При синхронном запуске ставьте timeout ≥ 180000 мс.

## Независимое ревью крупных пачек

После крупной пачки работ — не после каждой задачи — диапазон коммитов отдаётся на независимое ревью
в локально установленный Codex: он ходит другой моделью и видит то, чего не видит внутренний цикл.
Практика применяется постоянно, но до 2026-08-07 в этом файле её не было.

- **Оно окупается.** Замерено 2026-08-01: шесть настоящих замечаний в работе, уже прошедшей три
  внутренних адверсариальных круга, включая функциональный дефект — эвристика оглавления защищала
  короткую прозу, а анти-регрессионный тест на это проходил вакуумно. См.
  `docs/WHERE_WE_ARE.md`, раздел «Независимое ревью крупных пачек».
- **Оно ловит то, чего не ловит гард.** Статус спеки 055 двое суток утверждал «не начато» при уже
  влитой и замеренной работе; нашло это независимое ревью, а не тест. Спека 056 повторила ту же
  историю двумя днями позже.
- **Каждую находку проверяйте сами перед исправлением.** Из тех шести одна оказалась слабее
  заявленного, а первая попытка исправить главную завела в репозиторий словарь слов и нарушила
  Конституцию VII; правку пришлось упрощать обратно.
- **Внешнее ревью МОЖЕТ считать по данным — это утверждение исправлено 2026-08-09, и старая редакция
  стоила дня ручного счёта.** Здесь говорилось «читает код, но мерить не может»; неверно. Codex
  работает в ТОМ ЖЕ окружении: читает любой файл по абсолютному пути, включая gitignored, и выполняет
  Python (проверено: 3.12.5, `MINGW64_NT`). Закрыт ему только WSL — то есть наши тесты и пайплайн.
  Ошибка была в подмене «нет в git» → «недоступно»: дампы прогонов лежат ВНУТРИ каталога репозитория,
  просто в `.gitignore`, и читались всё это время. **Давайте ему абсолютные пути к данным и просите
  СЧИТАТЬ.** 2026-08-09 на просьбе независимо пересчитать величину, которую до этого считали два
  разных скрипта, он воспроизвёл её точно и нашёл класс записей, который оба пропустили из-за
  необоснованного пропуска в коде. Рабочая форма ответа — таблица «поднято / вердикт / замерено на
  книге»; образец в `specs/057-boundary-recovery-is-product-blind/spec.md`, раздел «Known limits of
  the rule».
- **Он ранжирует рассуждением, а не частотой.** 2026-08-09 три находки получили одинаковый P1, при
  том что одна срабатывала в 65 % случаев, а две другие требовали совпадения с событием, случающимся
  раз на 1 394. Переранжируйте сами или прямо просите оценить частоту и сказать, чем она измерена.
- **Находка обязана куда-то приземлиться**, и «просто починил» в этот список не входит:
  - гард-тест, который не даст дефекту вернуться (`tests/test_agent_contract_consistency.py`,
    `tests/test_where_we_are_freshness.py`, `tests/test_spec_status_consistency.py`);
  - запись в `## Changelog` затронутой спеки;
  - отдельная remediation-спека под `specs/<NNN>-<slug>/`, когда находок пачка — ревью-раунды 3–12
    закрыты спеками 036–043 и 051;
  - записанный ОТКАЗ с причиной: отклонённое предложение фиксируется в `## Non-goals` спеки, иначе оно
    возвращается — tagged-PDF предлагался четыре раза, см. раздел `## Non-goals` в
    `specs/055-pdf-docx-bridge-signal-loss/spec.md`.
- Отчёт ревью не является каноническим source of truth репозитория — правило в `docs/reviews/README.md`.
- Не путайте с ролью оркестратора: `docs/codex-orchestrator-rule.md` описывает Codex, управляющий
  субагентами, со Strict Gate на изменения файлов. Это другая задача.

### Как его запускать

Этого раздела здесь не было до 2026-08-09, и сам файл просил вписать его, когда команды заведутся.
Всё ниже проверено в работе, включая два способа сломаться.

**Найти бинарь — каждый раз заново, и брать САМЫЙ СВЕЖИЙ:**

```powershell
$codex = Get-ChildItem "$env:LOCALAPPDATA\OpenAI\Codex\bin" -Recurse -Filter codex.exe |
         Sort-Object LastWriteTime -Descending | Select-Object -First 1 -ExpandProperty FullName
```

Две ловушки, обе стоили прогона:

- **Каталог версии меняется при обновлениях.** За одну сессию 2026-08-07…09 он сменился с
  `d7e8094cfb76a267` на `cfac6bda2d141e07`, и захардкоженный путь перестал существовать.
- **`bin\codex.exe` в корне — НЕ шим, а отдельный старый билд.** На 2026-08-09 там 0.130.0-alpha.5
  против 0.147.0-alpha.6.5 в версионном каталоге, и он падает на текущем конфиге Codex в домашнем каталоге пользователя
  с ошибкой вида «Error loading config.toml: unknown variant default, expected fast or flex» —
  его конфиг лежит в домашнем каталоге пользователя и пишется новой версией.
  Поэтому именно `Sort-Object LastWriteTime -Descending`, а не корневой путь.

**Вызов** — промпт файлом через stdin, ответ в файл, обязательно в фоне (5–20 минут, 100–140k
токенов):

```powershell
Get-Content "<промпт.txt>" -Raw | & $codex exec --sandbox read-only - 2>&1 |
  Out-File -FilePath "<ответ.txt>" -Encoding utf8
```

`-` в конце `exec` — «промпт из stdin». `--sandbox read-only` — он ничего не изменит в репозитории.

**Читать ответ грепом, не целиком.** Codex повторяет промпт в начале, файл выходит на 5–7 тысяч
строк, и вердикт всегда в КОНЦЕ. Поэтому в промпте требуйте вердикт одной строкой из фиксированного
набора — иначе его не найти:

```bash
grep -n "СТРОИТЬ\|НЕ СТРОИТЬ\|ОСТАНОВИТЬСЯ" <ответ.txt> | tail -3
tail -150 <ответ.txt>
```

**Что обязательно в промпте:**

- **Границы возможностей первым абзацем — и они НЕ «ничего не можешь».** «Ты в том же окружении:
  читай файлы по абсолютным путям, включая исключённые из git, и считай сам, Python у тебя есть. WSL
  тебе закрыт, поэтому наши тесты и пайплайн ты не запустишь. НЕ ВЫДУМЫВАЙ измерений; число, которого
  нет в файлах, называй прогнозом и говори, чем его проверить.» Формулировка «ты ничего не можешь
  запустить» превращает его в генератор гипотез там, где он мог бы дать факт.
- **Никаких «атакуй», «сломай», «найди дыры».** Срабатывает фильтр безопасности и он отказывает,
  потратив контекст впустую. Писать «анализ устойчивости», «проверь корректность», «проверь
  фактическую точность».
- **Абсолютные пути к данным, если вопрос про данные.** Не «посмотри дампы» — а полный путь и
  описание полей. Оператор мерит сам только то, что требует WSL.
- **Требовать `file:line` на каждое возражение:** «находка без конкретного пути в коде не считается».
- **Просить возражать:** «возражение с конкретной ссылкой ценнее согласия».

**Лучший момент для вызова** — когда решение сформулировано, но ещё не построено. Ревью спеки 058 до
реализации переставило правило в другую точку кода и переопределило счётчик; те же замечания после
постройки стоили бы переделки. Ревью 057 после мержа тоже окупилось, но дороже.

**Если бинаря нет вовсе** — облачный контейнер, чужая VM, Linux без доступа к Windows-хосту, — не
изобретайте обход. Честных вариантов три, и они разобраны в
[`docs/CODEX_INDEPENDENT_REVIEW.md`](docs/CODEX_INDEPENDENT_REVIEW.md), раздел 6: оператор запускает
ваш промпт сам; либо работаете без Codex, **сказав это вслух в отчёте**; либо владелец решает ставить
Codex в облаке под свой ключ. Чего нельзя — объявлять внутренний адверсариальный проход независимым
ревью: вся ценность именно в другом движке.

Там же лежит развёрнутая инструкция по вызову: как находить бинарь, что писать в промпте и три
ловушки целиком. Этот раздел — короткая версия для тех, кто уже в контексте.

### Обязательная приёмка оркестратора: расширенное ревью по затронутым поверхностям

Правило введено владельцем 2026-11-06 и закрывает три пробела, которые этот раздел до того честно
называл отсутствующими: как передать диапазон, какой порог и куда класть отчёт.

**Когда.** После завершения работ по спеке: все рабочие ветки влиты в интеграционную ветку, полный
прогон `scripts/test.sh tests/ -q` зелёный в ГЛАВНОМ дереве, `git status --porcelain` пуст. Ревью
идёт ДО слияния в `main` и ДО того, как спека объявлена закрытой. Это шаг приёмки, а не
рекомендация: без него оркестратор не вправе написать «готово». Порог — любая работа уровня спеки
(одна `specs/<NNN>-…` или пачка связанных); одиночная правка в несколько строк ревью не требует.

**Что.** Codex `gpt-6-astra`, `--sandbox read-only`, по рецепту выше. Объём — **не дифф, а все
затронутые поверхности**: каждый модуль, в котором есть хотя бы один изменённый hunk, читается
ЦЕЛИКОМ; плюс прямые вызывающие и вызываемые изменённых функций; плюс тесты этих модулей. Список
строится из `git diff --stat <base>..<head>` и вручную расширяется до модулей и их соседей.
Ревью только диффа ловит ошибки в изменённых строках и пропускает те, что изменение создало в
неизменённых — ровно так 2026-11-06 двух реестров об одном абзаце не увидел ни один внутренний
проход.

**Как передать диапазон.** В промпте: base и head SHA, команда `git diff <base>..<head> --stat`
и `git log --oneline <base>..<head>` (git в его окружении есть, пусть выполнит сам), литеральный
список абсолютных путей поверхностей, путь к спеке. Отдельным абзацем — что уже измерено
оператором и чем (WSL ему закрыт).

**Что требовать в ответе.** `file:line` на каждую находку; частота и чем она измерена или что
это прогноз; уверенность; вердикт последней строкой из фиксированного набора. Возражение с
конкретной ссылкой ценнее согласия.

**Что делать с ответом.** Каждую находку оркестратор проверяет по коду сам (примерно одна из
шести слабее заявленного) и приземляет по списку выше: правка в той же ветке с тестом, запись в
Changelog спеки, или отказ в её Non-goals. Отчёт кладётся в `docs/reviews/` как
`CODEX_REVIEW_<NNN>_<YYYY-MM-DD>.md` вместе с промптом и таблицей «поднято / вердикт / замерено»;
по правилу `docs/reviews/README.md` он не является каноническим источником правды, им остаются
спека и код.

Чего в репозитории по-прежнему НЕТ: автоматической проверки, что ревью состоялось. Гард на это не
пишется: он не может отличить настоящий отчёт от формального.

### Оркестратор не делает работу сам

Правило владельца (сказано 2026-11-07 и 2026-11-08, повторено 2026-11-12); до 2026-11-12 оно жило
только в памяти ассистента, и сессия, начавшаяся без неё, снова делала всё своими руками.

- **Главная сессия управляет агентами, а не пишет код.** Работа уровня спеки — правило пайплайна,
  замер, тесты, документ — уходит агенту. Исключение одно: правка, для которой бриф дороже самой
  правки (строка в документе, статус, повтор гарда).
- **За оркестратором остаётся:** постановка задачи с уже измеренными фактами и путями к данным,
  слияние веток, канонический полный прогон в главном дереве, проверка каждого утверждения агента по
  коду и данным, приёмочное ревью Codex из раздела выше. Отчёт агента — заявка, а не доказательство:
  «зелёные тесты» и «ничего лишнего не задето» оркестратор перепроверяет сам.
- **Модель и усилие — по уровню задачи.** Механика (копирование, подсчёт, grep) — Haiku; ограниченная
  инженерная и работа с данными (скрипты замера, обвязка прогонов, сборка документов, чтение по
  рубрике) — Sonnet; правила пайплайна по форме с анти-вакуумными тестами и разбор находок ревью в
  ядре — Opus. Модель оркестратора — только оркестратору и суб-оркестратору. Между двумя ступенями
  берётся дешёвая; поднимать — когда отчёт показал, что задача была не по ней.
- **Агент, который пишет, получает своё дерево** — раздел «Боковые worktree для агентов». Агент,
  который только читает, работает в главном дереве и ничего в нём не меняет.
- **Параллельно идут только непересекающиеся работы:** делить по владению файлами, а не по темам.

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
- Для обычных UI-прогонов итоговые user-visible output artifacts пишутся в `.run/ui_results/` как stem-группа: `.result.md`, `.result.docx` и optional `.result.tts.txt`, `.result.tts.docx`, `.result.tts.pdf` и `.result.narration.json` для audiobook/narration сценариев (DOCX для ElevenLabs Studio и PDF собираются из тех же абзацев, что и `.tts.txt`; PDF может отсутствовать — причина в событии; `.result.narration.json` — файл книги для инструмента озвучки, сегменты в нём — те же тексты, что в `.tts.txt`, плюс паузы и словарь чтения; схема — `specs/073-narration-for-the-ear/contracts/narration-book.md`).
- Канонический лог-сигнал для этих файлов: `ui_result_artifacts_saved`. В его `artifact_paths` лежат точные пути к итоговому Markdown, DOCX и, когда файл записан, к `tts_text_path`, `tts_docx_path`, `tts_pdf_path`, `narration_book_path`.
- Для narration-specific анализа используйте `ui_audiobook_artifact_saved`: он указывает точные `tts_text_path`, `tts_docx_path`, `tts_pdf_path`, `narration_book_path` (`null`, если файла нет), статусы `narration_docx_status` / `narration_pdf_status` / `narration_book_status` и итог озвучки на прогон (спеки 070/072/073: `char_count`, `expected_paragraph_count`, `delivered_paragraph_count`, `excluded_count`, `needs_review_paragraph_count`, `heading1_count`, `studio_limits_exceeded` и др.). Поля `mode`, `tag_count`, `excluded_blocks` удалены спекой 070; полный перечень — `docs/LOGGING_AND_ARTIFACT_RETENTION.md` §5.5.
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

**Про «continuation plan», на который ссылается этот раздел.** Документ не назывался ни разу, и
единственный, где есть все три якоря (`5.0.1`, `## 11. False Direction Guard`, Workstream F), — это
`docs/archive/specs/STRUCTURE_RECOGNITION_COMPLETION_PLAN_2026-05-14.md`, про который раздел выше
говорит: документ архивный, расхождение с ним ничего не значит. Требовать сверки с документом, который
тут же объявлен незначащим, нельзя — эти три ссылки были самопротиворечием и с 2026-08-07 не являются
обязательными. Они оставлены как **исторический указатель**: там записано, какие направления уже
пробовали и почему отклонили, и это полезно прочитать — но источником правил служит свежий run report,
а не архив.

## Streamlit Layout Contract

- Для проблем с растянутой шириной, отступами и компоновкой сначала используйте нативные примитивы Streamlit: `st.set_page_config`, `st.columns`, `st.container`, `st.sidebar`, `width=`.
- **`use_container_width` в новом коде не писать.** В установленном Streamlit 1.64.0 параметр помечен deprecated и будет удалён (`.venv/lib/python3.13/site-packages/streamlit/elements/widgets/button.py`: параметры `use_container_width` и `width` у `st.button` — `:148-149`, у `st.download_button` — `:435-436`; пометка `.. deprecated::` — `:255-259`; отображение `True → "stretch"`, `False → "content"` — `:389-390`; проверено 2026-11-06). Замена ровно такая: `use_container_width=True` → `width="stretch"`, `use_container_width=False` → `width="content"`. До 2026-08-07 этот раздел рекомендовал обратное.
- Если пользователь явно просит без кастомных стилей, не решайте задачу через CSS-селекторы по DOM Streamlit; сначала меняйте layout-композицию штатными средствами Streamlit.
- Для UI/layout-проверки Streamlit используйте встроенный browser-editor/integrated browser как основной способ верификации результата.
- Не прогоняйте полный pytest suite по умолчанию после CSS-only или layout-only правок; для таких изменений сначала достаточно браузерной проверки и точечных тестов только если затронута Python-логика.
