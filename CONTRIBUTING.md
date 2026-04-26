# Contributing

## Локальная разработка

Проект использует основной Python runtime в WSL. Для штатной разработки, запуска приложения и shell-driven validation используйте `.venv/bin/activate` внутри WSL. Но перед выводом о broken env сначала фактологически проверьте layout `.venv`: в некоторых workspace агент может увидеть Windows layout (`.venv\Scripts\python.exe`) вместо Linux layout (`.venv/bin/activate`).

Startup performance contract считается частью канонической документации. Перед изменениями, затрагивающими старт приложения, сверяйтесь с `docs/STARTUP_PERFORMANCE_CONTRACT.md` и не меняйте startup path без явной задачи на performance или lifecycle.

1. Установите зависимости проекта через WSL setup entry point:

```bash
bash scripts/setup-wsl.sh
```

Из VS Code используйте `Tasks: Run Task -> Setup Project`. Этот путь устанавливает apt-пакеты из `system-requirements.apt`, создает `.venv`, ставит `requirements.txt` и проверяет `pandoc` + LibreOffice.

2. Ручной fallback: создайте виртуальное окружение:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Не создавайте Windows virtualenv в `.venv`: это перезапишет WSL-based runtime, на который опираются приложение и штатный тестовый путь.

Если для вспомогательных Windows-only сценариев всё же нужен отдельный venv, используйте другое имя каталога, например `.venv-win`, и не применяйте его для штатного запуска приложения или тестов:

```powershell
python -m venv .venv-win
.\.venv-win\Scripts\Activate.ps1
```

3. Ручной fallback: установите Python-зависимости:

```bash
pip install -r requirements.txt
```

4. Ручной fallback: установите system dependencies и проверьте `OPENAI_API_KEY` в `.env`:

```bash
sudo apt-get update
sudo apt-get install -y pandoc libreoffice antiword
soffice --headless --version
pandoc --version
```

5. Запустите приложение:

```bash
source .venv/bin/activate
streamlit run app.py
```

Если запуск идёт из Windows shell, используйте штатные wrappers или tasks, а не raw command chains:

```powershell
./scripts/start-project.ps1
```

## Видимый запуск тестов в VS Code

Основной путь через WSL tasks и `scripts/test.sh`:

```text
Tasks: Run Task -> Run Full Pytest
Tasks: Run Task -> Run Docker CI Parity Pytest
Tasks: Run Task -> Run Current Test File
Tasks: Run Task -> Run Current Test Node
```

Канонический CLI-путь из WSL:

```bash
bash scripts/test.sh tests/ -q
bash scripts/test.sh tests/test_config.py -vv
bash scripts/test.sh tests/test_config.py::test_name -vv -x
```

Важно различать два класса запуска:

- `bash scripts/test.sh ...` и shell-driven validation scripts являются **canonical contract path**.
- `python -m pytest ...` без этих shell entry points является только **debug path**.

Если текущий shell не WSL, но `.venv\Scripts\python.exe` и `pytest.exe` реально существуют и запускают тесты, агент может использовать этот путь только для обычных pytest selector-ов во время локального debugging:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_config.py -vv
```

Этот путь не заменяет shell-bound сценарии.

Низкоуровневый fallback во встроенном WSL-терминале VS Code:

```bash
bash -lc 'cd /mnt/d/www/projects/2025/DocxAICorrector && . .venv/bin/activate && pytest tests -q'
```

Для живого прогресса по каждому тесту:

```bash
bash -lc 'cd /mnt/d/www/projects/2025/DocxAICorrector && . .venv/bin/activate && pytest tests -vv'
```

WSL-driven tasks открывают отдельный терминал и оставляют его видимым после завершения.

## CI-Parity Debugging

Обычный WSL pytest нужен для быстрой обратной связи, но он не ловит все CI-only дефекты. Особенно это касается путей, завязанных на clean Ubuntu runtime, Python 3.12 и внешние системные конвертеры для legacy `.doc` и PDF import.

Что важно помнить:

- локальный `.venv` полезен для разработки, но не считается доказательством CI-совместимости;
- если менялись corpus tests, real-document extraction, legacy `.doc` normalization, PDF import или runtime conversion path, нужен отдельный parity run;
- для таких расследований проверяйте не только Python dependencies, но и `soffice`, `antiword`, `pandoc`.

Минимальный pre-push ritual:

1. `Tasks: Run Task -> Run Full Pytest`
2. `Tasks: Run Task -> Run Docker CI Parity Pytest`
3. при изменениях вокруг legacy `.doc`, PDF import или corpus validation: targeted runtime/application-flow tests и при необходимости отдельный прогон `tests/test_real_document_validation_corpus.py`

Предпочтительный user-visible parity path: `Tasks: Run Task -> Run Docker CI Parity Pytest`.

Низкоуровневый fallback из WSL-корня репозитория:

```bash
docker run --rm -v "$PWD":/src -w /src python:3.12 bash -lc '
	python -m venv /tmp/docxai-venv &&
	. /tmp/docxai-venv/bin/activate &&
	python -m pip install --upgrade pip &&
	pip install -r requirements.txt &&
	pytest tests/ -q
'
```

Точечный parity run для upload conversion/corpus path:

```bash
docker run --rm -v "$PWD":/src -w /src python:3.12 bash -lc '
	python -m venv /tmp/docxai-venv &&
	. /tmp/docxai-venv/bin/activate &&
	python -m pip install --upgrade pip &&
	pip install -r requirements.txt &&
	pytest tests/test_real_document_validation_corpus.py -vv -x --tb=short
'
```

Быстрые capability checks для legacy `.doc` и PDF conversion path:

```bash
command -v soffice || command -v libreoffice
command -v antiword
pandoc --version
```

PDF import использует LibreOffice Writer PDF import filter (`--infilter=writer_pdf_import`) и не выполняет OCR для scanned PDF.

Если clean Python 3.12 container и локальная WSL `.venv` расходятся по результату, приоритет для отладки CI имеет clean parity run.

## Real Document Validation

Канонический пользовательский путь:

```text
Tasks: Run Task -> Run Lietaer Real Validation
Tasks: Run Task -> Run Real Document Validation Profile
Tasks: Run Task -> Run Real Document Quality Gate
```

Канонический WSL CLI-путь:

```bash
bash scripts/run-real-document-validation.sh
bash scripts/run-real-document-quality-gate.sh
```

Не вызывайте `run_lietaer_validation.py` через Windows Python из WSL и не надейтесь на случайный shell cwd. Используйте только WSL `.venv` и репозиторный root.

Для AI agents и automation это правило расширяется:

- нельзя подменять `bash scripts/run-real-document-validation.sh` или `bash scripts/run-real-document-quality-gate.sh` прямым underlying Python runner-ом и описывать это как эквивалентный прогон;
- если canonical shell path недоступен в текущем runtime, это нужно явно сообщить как ограничение canonical verification;
- любой обходной прямой Python-запуск в таком сценарии может использоваться только как `debug-only`, а не как requested validation result.

Каждый прогон пишет уникальные артефакты в `tests/artifacts/real_document_pipeline/runs/<run_id>/`, обновляет latest manifest в `tests/artifacts/real_document_pipeline/lietaer_validation_latest.json` и live progress snapshot в `tests/artifacts/real_document_pipeline/lietaer_validation_progress.json`.

Для registry-driven запуска произвольного документа используйте `Run Real Document Validation Profile`; canonical Lietaer task остаётся коротким видимым entrypoint для основного regression target.

Exceptional quality gate не входит в обычный полный прогон и должен запускаться только через выделенную task/script. Этот путь сам проверяет latest manifest/report и не требует ручных скриншотов терминала.

Если вы ссылаетесь на real-document прогон в PR или review, указывайте `run_id` и путь к run-specific report.

## Перед pull request

Перед отправкой изменений выполняйте полный прогон через канонический WSL entry point:

```bash
bash scripts/test.sh tests/ -q
```

Низкоуровневый fallback в каноническом WSL-окружении:

```bash
source .venv/bin/activate
pytest tests -q
```

Если правки затрагивают UI или блокировку документа, проверьте также ручной smoke-test на небольшом `.docx`.

Если правки затрагивают test workflow contract, нельзя ограничиваться одной точкой изменений. В одном change-set должны быть синхронизированы:

- `scripts/test.sh`;
- `.vscode/tasks.json` test tasks;
- `tests/test_script_workflow_smoke.py`;
- `README.md`, `CONTRIBUTING.md`, `docs/WORKFLOW_AND_IMAGE_MODES.md`.

Минимальная обязательная проверка после таких правок:

```bash
bash scripts/test.sh tests/test_script_workflow_smoke.py -q
bash scripts/test.sh tests/ -q
```

## Шрифты выходного документа

По умолчанию Pandoc-reference document, через который строится выходной DOCX,
использует встроенную тему python-docx: **Cambria** для текста и **Calibri** для
заголовков. Явно переопределить это можно через секцию `[output.fonts]` в
`config.toml`:

```toml
[output.fonts]
body    = "Aptos"          # Normal, List Paragraph, Caption, Table
heading = "Aptos Display"  # Heading 1–6
```

Те же параметры доступны через переменные среды (env-значение имеет приоритет
над `config.toml`):

```
DOCX_AI_OUTPUT_BODY_FONT=Arial
DOCX_AI_OUTPUT_HEADING_FONT=Georgia
```

**Когда секция отсутствует** — тема не трогается, а reference-document остаётся
на штатных стилевых значениях проекта.

**Архитектурный контекст.** Для обычного текста, подписей, списков и таблиц
reference-document использует прямые `w:rFonts`, поэтому `body` применяется
непосредственно к этим стилям. Для заголовков этого недостаточно: у built-in
Heading styles уже есть `w:asciiTheme="majorHAnsi"`, а Word даёт theme-binding
приоритет над прямым `style.font.name`. Поэтому `heading` дополнительно патчит
`word/theme/theme1.xml` в reference-документе (см. `generation._patch_reference_theme_fonts`).
Именно комбинация прямого style override для body-стилей и theme patch для
heading-стилей даёт корректный результат.

## UI-стили и HTML

Для UI в этом проекте действует жёсткий порядок выбора решения:

1. Сначала использовать native Streamlit-компоненты (`st.info`, `st.warning`, `st.caption`, `st.metric`, `st.progress`, `st.columns`, `st.expander`).
2. Если нужен client-side state без server rerun и приходится использовать `components.html(...)`, оформлять это как один централизованный component-contract с единым theme/layout helper.
3. Только в последнюю очередь использовать локальный HTML/CSS workaround.

Практические правила:

- не рассчитывайте, что iframe из `components.html(...)` унаследует стили основного приложения;
- не добавляйте `font-family` override без отдельной задачи на типографику;
- не размазывайте inline CSS по разным UI-функциям — либо native Streamlit, либо один helper/contract на компонент;
- `unsafe_allow_html=True` допустим только для узких, явно ограниченных поверхностей, где native Streamlit не покрывает нужный UX-контракт.

### Как проверять правки визуала без полного pytest-прогона

Для быстрых UI-итераций не нужно каждый раз ждать полный тестовый прогон или повторный полный processing run документа.

Короткий цикл проверки для `markdown preview`:

1. Откройте приложение в integrated browser VS Code.
2. Запустите реальную обработку документа или дождитесь, когда появится `Текущий Markdown` / `Предпросмотр Markdown`.
3. Откройте preview прямо во время обработки: partial preview обновляется по мере готовности блоков.
4. Для быстрой визуальной отладки правьте CSS прямо в DOM iframe через browser tools и сразу смотрите результат на текущей странице.
5. Только после того как визуально найден правильный вариант, переносите его в `ui.py` в централизованный helper `_MARKDOWN_PREVIEW_THEME_CSS`.

Важно:

- DOM/CSS-правки в браузере временные и исчезают после rerun/reload;
- финальная постоянная правка всё равно должна жить в коде, а не в ручной browser-инъекции;
- для окончательной проверки поведения используйте обычный test path, но быстрый visual tuning допустимо делать без полного pytest между каждой CSS-итерацией.

### Почему Streamlit-стили не попадают в markdown preview автоматически

`render_markdown_preview(...)` использует `streamlit.components.v1.components.html(...)`, а значит preview рендерится как отдельный `about:srcdoc` iframe со своим DOM и своим `<style>`.

Следствия:

- CSS и theme основного Streamlit-приложения не наследуются внутрь iframe;
- `secondaryBackgroundColor`, `textColor` и другие theme-значения из `.streamlit/config.toml` не применяются автоматически внутри preview;
- чтобы iframe выглядел согласованно со Streamlit, ему нужен собственный централизованный theme shell, который вручную повторяет нужные цвета/контраст/spacing.

Канонический паттерн для этого проекта:

- считайте markdown preview отдельным документом, а не частью Streamlit DOM;
- не пытайтесь «починить наследование» между родительским приложением и iframe, потому что этого наследования нет;
- постоянное решение для preview — во время рендера синхронизировать внутри iframe реальные computed styles родительского Streamlit DOM: цвет текста, фон controls, border, radius, типографику и другие визуальные токены;
- если preview снова начнёт выглядеть как browser-default control set, это означает, что синхронизация parent styles сломалась или не выполнилась, а не то, что Streamlit theme внезапно перестал наследоваться.

Дополнительный operational нюанс этого репозитория:

- в `.streamlit/config.toml` выставлены `fileWatcherType = "none"` и `runOnSave = false`;
- поэтому изменение `ui.py` на диске не обязано мгновенно попадать в уже работающий runtime;
- quick visual tuning делается через browser DOM, а постоянный кодовый результат подтверждается уже после нового исполнения обновлённого Python-кода.

## Правила изменений

- Держите изменения узкими и без побочных рефакторингов.
- Не меняйте поведение системного промпта без явной задачи на качество модели.
- Для регрессий сначала фиксируйте контракт тестом, затем кодом.
- При изменении структуры модулей синхронизируйте `README.md`, а historical decomposition docs обновляйте только если это действительно нужно для архивного контекста.

## Pull request checklist

- Изменение объяснено в описании PR.
- Тесты проходят локально.
- Документация обновлена, если менялось поведение или структура проекта.
- Лишние временные файлы не попали в коммит.
- Если менялся test workflow contract, синхронно обновлены `scripts/test.sh`, `.vscode/tasks.json`, `tests/test_script_workflow_smoke.py`, `README.md`, `CONTRIBUTING.md`, `docs/WORKFLOW_AND_IMAGE_MODES.md`, а CI остаётся на `bash scripts/test.sh ...`.
- Если менялся startup path, сверена `docs/STARTUP_PERFORMANCE_CONTRACT.md`, обновлены startup-related tests и отдельно проверен first useful render после cold start.
- Для финальной локальной верификации в VS Code использован видимый пользовательский путь запуска тестов, а не hidden terminal capture.
