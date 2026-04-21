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

## Перед первым ad-hoc запуском тестов

- Сначала решите, нужен ли вообще shell-run: для финальной верификации в VS Code сначала предпочитайте existing tasks `Run Full Pytest`, `Run Current Test File`, `Run Current Test Node`.
- Перед первым ручным test command обязательно определите текущий shell через `uname` и `pwd`, а не по предположению.
- Если `uname` показывает Linux и рабочий каталог уже под `/mnt/d/www/projects/2025/DocxAICorrector`, вы уже внутри WSL runtime: запускайте `bash scripts/test.sh ...` напрямую.
- Если shell показывает `MSYS_NT`, `MINGW64_NT`, Windows PowerShell или иной не-WSL runtime, используйте `wsl.exe -d Debian ...` только как transport layer до project WSL runtime.
- Никогда не вкладывайте `wsl.exe` внутрь shell, который уже находится в WSL: это даёт ложные path/stdio проблемы и ломает диагностику.
- Для одного расследования держите только один активный pytest run на один selector и дождитесь его окончания перед следующим запуском.
- Для CI-parity сначала подтвердите SHA failing run. Если локальный worktree грязный или уже ушёл вперёд относительно tested commit, используйте clean worktree или готовый Docker CI-parity path прежде чем трактовать результат как репрезентативный.

## Финальная верификация для агентов

- Для финальной верификации внутри VS Code предпочитайте user-visible task path, а не agent-side shell capture.
- Если подходящий existing task есть, используйте именно его как финальный proof path: `Run Full Pytest`, `Run Current Test File`, `Run Current Test Node` или другой repo task того же класса.
- Не считайте вывод из agent terminal, даже если он корректный, эквивалентом user-visible verification в VS Code terminal panel.
- Если shell capture на отдельных pytest node-ах нестабилен или неполон, не упирайтесь в него как в финальный источник истины; переходите на user-visible task path.
- Shell/Python reruns можно использовать для debugging, но финальное утверждение о результате должно опираться на user-visible task path, когда для этого есть подходящий task.

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

## Запрещено

- `py -m pytest` из Windows shell.
- Запуск `pytest` через PowerShell bridge / PowerShell wrapper.
- Создание Windows virtualenv в `.venv`.
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
- `docs/LOGGING_AND_ARTIFACT_RETENTION.md`
- `.github/copilot-instructions.md`

## UI result artifacts

- Не путайте `.run/completed_*` с итоговым результатом обработки: `completed_*` — это persisted cache исходного загруженного файла для restart/reuse после успешного прогона, а не output DOCX.
- Для обычных UI-прогонов итоговые user-visible output artifacts пишутся в `.run/ui_results/` как пара файлов одного stem: `.result.md` и `.result.docx`.
- Канонический лог-сигнал для этих файлов: `ui_result_artifacts_saved`. В его `artifact_paths` лежат точные пути к итоговому Markdown и итоговому DOCX.
- Если нужно анализировать качество последнего UI-прогона, сначала ищите `ui_result_artifacts_saved` и соответствующие файлы в `.run/ui_results/`, а уже потом fallback'айтесь к промежуточным diagnostics.

## Streamlit Layout Contract

- Для проблем с растянутой шириной, отступами и компоновкой сначала используйте нативные примитивы Streamlit: `st.set_page_config`, `st.columns`, `st.container`, `st.sidebar`, `use_container_width`.
- Если пользователь явно просит без кастомных стилей, не решайте задачу через CSS-селекторы по DOM Streamlit; сначала меняйте layout-композицию штатными средствами Streamlit.
- Для UI/layout-проверки Streamlit используйте встроенный browser-editor/integrated browser как основной способ верификации результата.
- Не прогоняйте полный pytest suite по умолчанию после CSS-only или layout-only правок; для таких изменений сначала достаточно браузерной проверки и точечных тестов только если затронута Python-логика.
