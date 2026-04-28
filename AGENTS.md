# AGENTS.md

Короткий front-door для ассистентов и automation в этом репозитории.

## Runtime Contract

### Fast routing for agents

- Если задача про pytest verification, используйте existing VS Code pytest task для user-visible proof или `bash scripts/test.sh ...` внутри уже подтверждённого WSL shell.
- Если задача про structural preparation snapshot/diagnostic для real-document profile, используйте `bash scripts/run-structural-preparation-diagnostic.sh <document_profile_id> [--run-profile-id <id>]` в WSL или task `Run Structural Preparation Diagnostic`.
- Не собирайте такой snapshot через вложенный `python -c ...` с JSON-печатью, если `real_document_validation_structural.py` уже покрывает этот вывод как CLI.

Проверенные command sets для structural snapshot:

```bash
# 1) Preferred user-visible path in VS Code task
# Task: Run Structural Preparation Diagnostic
# Prompt 1: end-times-pdf-core
# Prompt 2: leave blank to use document_profile.structural_run_profile from corpus_registry.toml

# 2) Direct WSL shell path with explicit run profile override
bash scripts/run-structural-preparation-diagnostic.sh end-times-pdf-core --run-profile-id ui-parity-pdf-structural-recovery

# 3) File-capture fallback when stdout transport is fragile
bash scripts/run-structural-preparation-diagnostic.sh end-times-pdf-core --run-profile-id ui-parity-pdf-structural-recovery > .run/end_times_structural_snapshot.json 2>&1

# 4) Inspect saved snapshot in the same WSL shell
tail -n 40 .run/end_times_structural_snapshot.json
```

- Для task `Run Structural Preparation Diagnostic` второй prompt сейчас безопасно использовать пустым; явный `--run-profile-id ...` лучше задавать через прямой shell path выше, чтобы не зависеть от task quoting.

- Канонический project runtime: WSL project runtime по пути `/mnt/d/www/projects/2025/DocxAICorrector`.
- Для тестов, диагностических импортов, проверки зависимостей и runtime-выводов источником истины считается project runtime внутри WSL.
- Но агент НЕ имеет права предполагать layout `.venv` заранее: сначала нужно фактологически проверить, это WSL/Linux env (`.venv/bin/activate`) или Windows env (`.venv\Scripts\python.exe`).
- Если фактический layout `.venv` расходится с ожидаемым контрактом, агент должен явно зафиксировать это как состояние workspace и выбрать рабочий runnable path вместо ложного вывода, что тесты "не запускаются".
- Canonical setup для нового WSL/server runtime: `bash scripts/setup-wsl.sh` или VS Code task `Setup Project`; Python dependencies живут в `requirements.txt`, WSL system dependencies — в `system-requirements.apt`.
- PDF import требует LibreOffice (`soffice`/`libreoffice`) внутри WSL и использует Writer PDF import filter `--infilter=writer_pdf_import`; не называйте env готовым для PDF без проверки LibreOffice availability.

## Canonical Test Commands

Используйте только канонический entry point:

```bash
bash scripts/test.sh tests/ -q
bash scripts/test.sh tests/test_file.py -vv
bash scripts/test.sh tests/test_file.py::test_name -vv -x
```

Не запускайте тесты через `py -m pytest`, `python -m pytest` или PowerShell, если явно не подтверждено, что команда выполняется именно внутри project WSL runtime.

Критическое различие:

- `bash scripts/test.sh ...`, `bash scripts/run-real-document-validation.sh`, `bash scripts/run-real-document-quality-gate.sh` и любые тесты/spec-paths, которые сами завязаны на shell entrypoint, считаются **canonical contract path**.
- Прямой запуск `pytest` или underlying Python runner без этого shell entrypoint считается только **debug path**, а не эквивалентом canonical contract path.

Если нужен низкоуровневый fallback, сначала активируйте project env внутри WSL:

```bash
source .venv/bin/activate
pytest tests/ -q
```

## Перед первым ad-hoc запуском тестов

- Сначала решите, нужен ли вообще shell-run: для финальной верификации в VS Code сначала предпочитайте existing tasks `Run Full Pytest`, `Run Current Test File`, `Run Current Test Node`.
- Перед первым ручным test command обязательно определите текущий shell через `uname` и `pwd`, а не по предположению.
- До любого вывода о broken env обязательно проверьте layout `.venv`: наличие `.venv/bin/activate`, `.venv/bin/python`, `.venv/Scripts/python.exe`, `.venv/Scripts/pytest.exe`.
- Если `uname` показывает Linux и рабочий каталог уже под `/mnt/d/www/projects/2025/DocxAICorrector`, вы уже внутри WSL runtime: запускайте `bash scripts/test.sh ...` напрямую.
- Если shell показывает `MSYS_NT`, `MINGW64_NT`, Windows PowerShell или иной не-WSL runtime, используйте `wsl.exe -d Debian ...` только как transport layer до project WSL runtime.
- Если shell не WSL, но `.venv/Scripts/python.exe` и `pytest.exe` существуют и реально запускают тесты, это допустимый agent-side debug path для локальной проверки изменённого кода. Не называйте такой env broken только потому, что он не WSL-layout.
- Если конкретный selector/test helper внутри себя жёстко вызывает canonical shell script или WSL-only validation path, Windows `.venv/Scripts/python.exe -m pytest ...` НЕ является заменой этого selector-а. В таком случае Windows path допустим только для исследования кода вокруг проблемы, но не как выполнение исходного shell-bound test contract.
- Никогда не вкладывайте `wsl.exe` внутрь shell, который уже находится в WSL: это даёт ложные path/stdio проблемы и ломает диагностику.
- Для одного расследования держите только один активный pytest run на один selector и дождитесь его окончания перед следующим запуском.
- Для CI-parity сначала подтвердите SHA failing run. Если локальный worktree грязный или уже ушёл вперёд относительно tested commit, используйте clean worktree или готовый Docker CI-parity path прежде чем трактовать результат как репрезентативный.
- Для проверки конкретного GitHub Actions run нельзя объявлять `passed` или `failed`, пока этот run не имеет явного финального состояния `completed` с `conclusion`.
- Если run-page или список Actions просматриваются без авторизации и не дают logs/tests annotations, считайте web-статус предварительным и подтверждайте проблему canonical локальным прогоном.
- Если в web snapshot run ещё `queued`/`in progress`, явно сообщайте, что итог run неизвестен; не делайте финальный вывод до завершения.
- Если пользователь даёт прямое подтверждение (например, email summary о failed tests), а web snapshot противоречит этому, приоритет — воспроизвести failing scope локально и явно отметить расхождение источников.

## Финальная верификация для агентов

- Для финальной верификации внутри VS Code предпочитайте user-visible task path, а не agent-side shell capture.
- Если подходящий existing task есть, используйте именно его как финальный proof path: `Run Full Pytest`, `Run Current Test File`, `Run Current Test Node` или другой repo task того же класса.
- Не считайте вывод из agent terminal, даже если он корректный, эквивалентом user-visible verification в VS Code terminal panel.
- Если shell capture на отдельных pytest node-ах нестабилен или неполон, не упирайтесь в него как в финальный источник истины; переходите на user-visible task path.
- Shell/Python reruns можно использовать для debugging, но финальное утверждение о результате должно опираться на user-visible task path, когда для этого есть подходящий task.
- Для shell-bound validation/spec/UI-parity сценариев debug run через другой entrypoint никогда не должен описываться как выполнение исходного requested test. Он может подтверждать только внутреннюю гипотезу, но не заменяет canonical validation result.

## Canonical vs Debug Path

- **Canonical path**: именно тот entrypoint, который просит репозиторный контракт или сам тестовый selector: `scripts/test.sh`, `scripts/run-real-document-validation.sh`, `scripts/run-real-document-quality-gate.sh`, существующие VS Code tasks или прямой WSL-run того же shell entrypoint.
- **Debug path**: любой обходной запуск, используемый для локальной диагностики, например `./.venv/Scripts/python.exe -m pytest ...`, прямой импорт runner-модуля или узкий internal helper.
- Если requested selector сам проверяет shell-bound contract, debug path не является доказательством выполнения requested selector-а.
- Нельзя подменять canonical path на debug path молча. В ответе нужно явно маркировать это как `debug-only`, если пользователь не просил именно обходной запуск.
- Для `real`, `spec`, `ui-parity`, `validation`, `quality-gate` и shell-script driven сценариев canonical path имеет абсолютный приоритет над debug path.
- Если canonical path недоступен в текущем runtime, агент должен сообщить именно это ограничение, а не писать, что requested test был выполнен эквивалентно другим способом.
- Для structural preparation snapshot path `scripts/run-structural-preparation-diagnostic.sh` и task `Run Structural Preparation Diagnostic` считаются preferred diagnostic entrypoints поверх ad-hoc `python -c`.
- Если нужен persisted snapshot для последующего чтения, сохраняйте stdout CLI в workspace file вроде `.run/end_times_structural_snapshot.json`, а не во временный ad-hoc Python one-liner.

### Если pytest output неполный или обрывается

- Частичный или оборванный stdout/stderr после `wsl.exe ... pytest ...` трактуйте сначала как transport/capture problem, а не как тестовый результат.
- Не делайте вывод `passed`/`failed` по неполному capture и не пересказывайте его пользователю как завершённый прогон.
- Для debugging держите один pytest selector на одну команду: один файл или один node, но не несколько селекторов подряд и не несколько pytest-вызовов в одной строке.
- Если file-level selector снова даёт неполный поток, сужайте прогон до node selector по наиболее затронутому сценарию, чтобы получить короткий и завершённый вывод.
- Если у агента уже есть прямой WSL shell или user-visible VS Code task для того же селектора, предпочитайте его повторному прогону через хрупкий `wsl.exe` bridge.
- Если debugging потребовал agent-side fallback, повторите финальное подтверждение через подходящий user-visible task и только после этого заявляйте результат пользователю.

## КРИТИЧЕСКИ ВАЖНО: shell identity для Bash tool

Не предполагайте тип shell заранее: агентский terminal/tooling может оказаться **MSYS/Git Bash**, **PowerShell** или уже быть присоединён к **WSL bash**.

Признаки MSYS shell (не WSL):
- `uname` показывает `MSYS_NT-...` или `MINGW64_NT-...`
- `pwd` возвращает `/d/www/...` (не `/mnt/d/...`)
- `/mnt/d/...` пути не существуют
- `.venv/bin/pytest` не запускается: шебанг `#!/mnt/d/.../python3` сломан в MSYS

Признаки WSL shell:
- `uname` показывает `Linux ...microsoft-standard-WSL2...`
- `/mnt/d/www/...` пути существуют
- `.venv/bin/activate` и `pytest` работают корректно

### Корректный способ запустить тесты после определения shell

Если shell уже WSL:

```bash
bash scripts/test.sh tests/ -q
```

Если shell не WSL, но `.venv/Scripts/python.exe` существует и `pytest` установлен:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/ -q
```

Этот путь допустим только для обычных pytest selector-ов, которые не зависят от shell-bound contract внутри себя.

Если shell не WSL и нужен agent-side debug run:

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
- Если `uname` уже показывает Linux и `pwd` уже под `/mnt/d/...`, не используйте `wsl.exe` повторно.
- Всегда `wsl.exe`, не `wsl` (MSYS может не иметь `wsl` в PATH).
- Всегда `echo START && ... && echo DONE` — без этого вывод теряется.
- Всегда `2>&1` — stderr тоже буферизуется отдельно.

`scripts/test.sh` НЕ работает из Bash tool напрямую — скрипт вызывает `exec pytest`, и `pytest` не находится в PATH MSYS окружения.

Если `wsl.exe` path неработоспособен из-за отсутствия `.venv/bin/activate`, но Windows `.venv\Scripts\python.exe` реально запускает тесты с проектными зависимостями, используйте Windows venv для debugging вместо ложного вывода, что runtime verification полностью заблокирована.

Исключение: если проверяемый сценарий привязан к canonical shell script, real-document validation, UI-parity harness, quality gate или другому WSL-only contract path, Windows venv не заменяет requested verification и может использоваться только как debug-only path.

## Запрещено

- `py -m pytest` из Windows shell.
- Запуск `pytest` через PowerShell bridge / PowerShell wrapper.
- Заявлять, что тесты "не запускаются" или что env broken, не проверив фактические executable paths в `.venv`.
- Подменять shell-bound spec/validation test другим underlying Python runner-ом и описывать это как эквивалент requested test execution.
- Подменять `real`, `spec`, `ui-parity`, `validation`, `quality-gate` сценарий debug path-ом без явной маркировки, что canonical path не был выполнен.
- Запуск `bash scripts/test.sh ...` или `source .venv/bin/activate && pytest` напрямую из Bash tool без `wsl.exe -d Debian bash -c '...'`.
- Голое `wsl` вместо `wsl.exe` из агентского терминала.
- WSL-команды без echo-маркеров (вывод теряется).

## Надёжный вызов WSL из агентского терминала

Этот раздел применяйте только если предыдущая проверка показала, что текущий shell ещё не WSL.

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

Если даже с echo-маркерами вывод остаётся частичным, считайте это деградацией канала захвата. В таком случае:

- не расширяйте прогон до нового file-level/full-suite запуска ради "подтверждения";
- переходите на более узкий одиночный selector;
- при наличии подходящего existing task используйте его как финальный proof path вместо повторных agent-side rerun через тот же bridge.
- не запускайте второй pytest run параллельно первому только чтобы "проверить ещё раз"; сначала дочитай и сузь текущий selector.

### Когда допустим PowerShell и как его вызывать правильно

PowerShell допустим только для read-only Windows-side диагностики, когда нужно:

- посчитать метрики по файлам или строкам;
- обойти нестабильный WSL stdout capture;
- быстро проверить содержимое workspace без запуска project runtime.

Для тестов, импортов runtime и любой финальной верификации это правило не отменяет WSL-first contract.

Правильный путь для агентских команд:

1. Не делайте nested shell chain вида `cmd.exe -> powershell.exe -> ...`.
2. Не создавайте временный `.ps1` в WSL-пути вроде `/tmp/...` и не передавайте его в Windows PowerShell через `-File`.
3. Если нужен скрипт, создавайте его в Windows-доступном пути, например `C:\Users\admin\AppData\Local\Temp\...`.
4. При запуске файла используйте `powershell.exe -NoProfile -ExecutionPolicy Bypass -File "C:\...\script.ps1"`.
5. Если хватает однострочника, предпочитайте прямой `powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "..."` без промежуточного `cmd.exe`.
6. Для многострочного PowerShell не вкладывайте сложные переменные и циклы в несколько уровней shell quoting; лучше вынести их в временный Windows-side `.ps1`.

Практические причины:

- nested quoting ломает `$var`, `foreach(...)` и кавычки ещё до того, как код доходит до PowerShell;
- PowerShell из Windows не видит WSL-пути вида `/tmp/...` как валидный аргумент для `-File`;
- execution policy может блокировать `.ps1`, поэтому нужен `-ExecutionPolicy Bypass`;
- для read-only метрик PowerShell полезен, но он не должен подменять WSL runtime contract.
- если нужен structural snapshot из WSL runtime, PowerShell должен только транспортировать вызов task/script; не встраивайте в него вложенный `python -c` с JSON и импортами.

Надёжные шаблоны:

```bash
# Read-only однострочник из агентского терминала
echo START && powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "<POWERSHELL>" && echo DONE

# Read-only многострочный скрипт
# 1) записать файл в Windows temp
# 2) запустить его так:
echo START && powershell.exe -NoProfile -ExecutionPolicy Bypass -File "C:\Users\admin\AppData\Local\Temp\agent_check.ps1" && echo DONE
```

Антипаттерны:

- `cmd.exe /c powershell.exe ...` без явной необходимости;
- `powershell.exe -File /tmp/script.ps1`;
- сложный PowerShell-код, встроенный в `wsl.exe -d Debian bash -lc "..."`;
- использование PowerShell как обходного пути для pytest verification.

### Долгие команды

- Pyright, mypy и другие type-checkers работают 40–120 секунд.
- Используйте `mode=async` и `get_terminal_output` с ожиданием; не считайте пустой вывод признаком зависания.
- При `mode=sync` ставьте `timeout` не менее 180000 мс для type-checking команд.

## Extended Canonical Docs

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

## Streamlit Layout Contract

- Для проблем с растянутой шириной, отступами и компоновкой сначала используйте нативные примитивы Streamlit: `st.set_page_config`, `st.columns`, `st.container`, `st.sidebar`, `use_container_width`.
- Если пользователь явно просит без кастомных стилей, не решайте задачу через CSS-селекторы по DOM Streamlit; сначала меняйте layout-композицию штатными средствами Streamlit.
- Для UI/layout-проверки Streamlit используйте встроенный browser-editor/integrated browser как основной способ верификации результата.
- Не прогоняйте полный pytest suite по умолчанию после CSS-only или layout-only правок; для таких изменений сначала достаточно браузерной проверки и точечных тестов только если затронута Python-логика.
