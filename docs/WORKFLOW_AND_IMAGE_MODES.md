# Current Workflow And Image Modes

Этот документ является единственным актуальным source of truth для двух поверхностей, которые чаще всего drift-ят при локальных изменениях:

- dev/runtime workflow;
- пользовательские image modes и их фактический delivery contract.

Если другой markdown-документ в `docs/` формулирует эти контракты иначе, приоритет всегда у этого файла. Historical, point-in-time и superseded материалы перечислены в `docs/ARCHIVE_INDEX.md`.

## Runtime Workflow

- Единственный runtime для Python, pytest, Streamlit, Pandoc и LibreOffice-конвертации: WSL `.venv` плюс WSL system packages.
- Windows PowerShell используется только как thin wrapper и transport layer для lifecycle/diagnostic scripts и соответствующих VS Code tasks.
- Каталог `.venv-win/` допустим только для editor tooling и статического анализа; он не должен участвовать в runtime auto-selection.
- Агентам и automation запрещено предполагать layout `.venv` заранее: сначала нужно проверять, существует ли WSL/Linux layout (`.venv/bin/activate`) или Windows layout (`.venv\Scripts\python.exe`).
- Setup source of truth для нового WSL/server runtime: `system-requirements.apt` для apt-пакетов, `requirements.txt` для Python-пакетов, `scripts/setup-wsl.sh` как canonical bootstrap, VS Code task `Setup Project` как user-visible wrapper.
- Upload contract больше не DOCX-only: пользовательский вход может быть `.docx`, legacy `.doc` или `PDF`; после boundary в `processing_runtime.py` downstream-слои обязаны работать с normalized DOCX bytes, но для legacy `.doc` и `PDF` token identity остаётся привязанной к исходным source bytes.
- Предпочтительный backend автоконвертации legacy `.doc` внутри WSL: `LibreOffice` / `soffice`; fallback backend: `antiword` + `pandoc`.
- PDF import uses the deterministic text-layer importer for selectable-text PDFs.
  LibreOffice `writer_pdf_import` is no longer the runtime PDF fallback; OCR for
  scanned PDF remains outside the current proof contract unless explicitly
  enabled.
- Картинки PDF (спека 082, срез A): выданная картинка в пространстве краски (`Separation`/`DeviceN`, в том числе под
  `Indexed`; так хранятся, например, фото долями краски), которая к тому же антикоррелирует с отрисовкой своей рамки
  (негатив страницы), приходит в DOCX PNG-отрисовкой своей рамки страницы — `pypdfium2` из `requirements.txt`, системного
  пакета нет — с размером рамки. Если поверх рамки чужой текст или картинка, в словаре картинки `/SMask` или `/Mask`,
  размещение повёрнуто или зеркально, рамка выходит за `CropBox`, страница с `/UserUnit` или текст получен через OCR —
  картинка остаётся как выдана; любой сбой шага тоже оставляет картинку как выдана. Дальше это обычная картинка: режимы изображений ниже обращаются
  с ней как с любой другой, текст документа не меняется.
- Официальные entry points для setup, запуска и диагностики: `Setup Project`, `Project Status`, `Start Project`, `Stop Project`, `Run Full Pytest`, `Run Current Test File`, `Run Current Test Node`, `Tail Streamlit Log`.
- Официальные видимые real-document entry points: `Run Lietaer Real Validation`, `Run Real Document Validation Profile`, `Run Real Document Quality Gate`.
- Полный `Run Full Pytest` не должен неявно запускать дорогой real-document AI smoke только потому, что в `.env` присутствует `OPENAI_API_KEY`; для такого smoke требуется явный opt-in.
- Официальный тестовый entry point: `bash scripts/test.sh ...` из WSL или VS Code tasks, которые вызывают WSL/bash напрямую.
- `bash scripts/test.sh ...`, `bash scripts/run-real-document-validation.sh`, `bash scripts/run-real-document-quality-gate.sh` и соответствующие VS Code tasks являются **canonical contract path**.
- Прямой `pytest` через `python -m pytest` без этих shell entry points является только **debug path**.
- Если текущий workspace фактически содержит Windows layout `.venv` и `.venv\Scripts\python.exe -m pytest ...` реально работает, этот путь допустим только для локального debugging обычных pytest selector-ов.
- Для `real`, `spec`, `ui-parity`, `validation`, `quality-gate` и любых shell-driven сценариев debug path не заменяет canonical verification path.
- Если requested selector сам вызывает shell-bound contract, нельзя описывать direct Python rerun как выполнение исходного selector-а; такой rerun должен маркироваться как `debug-only`.
- Для agent-side debug запусков pytest должен выполняться по одному selector за команду; нельзя склеивать несколько прогонов через `&&` или уводить их в hidden/background terminal, если нужен полный и наблюдаемый результат.
- Официальные PowerShell wrappers: `scripts/start-project.ps1`, `scripts/stop-project.ps1`, `scripts/status-project.ps1`, `scripts/tail-streamlit-log.ps1`.
- Вся command logic живёт в `scripts/project-control-wsl.sh` и `scripts/test.sh`; lifecycle wrappers и tasks не должны дублировать raw streamlit or pytest command chains.
- Workflow contract coverage разделена: `tests/test_script_contract_static.py` несёт CI-safe static workflow/task/docs/script checks, а `tests/test_script_workflow_smoke.py` оставлен для env-sensitive subprocess/PowerShell/WSL smoke.
- `DOCXAI_SKIP_WORKFLOW_SMOKE=1` может отключать только env-sensitive smoke; он не должен выключать `tests/test_script_contract_static.py`.

## CI Parity Debugging Contract

- Локальный WSL `.venv` остаётся source of truth для обычной разработки, но сам по себе не доказывает CI-совместимость.
- Для расследования CI-only regressions нужен отдельный clean-environment parity run на Python 3.12, потому что CI job `tests` выполняется именно на таком runtime.
- Для багов вокруг upload normalization (`.doc`, `PDF`), corpus validation и real-document extraction проверяйте не только Python packages, но и системные бинарники: `soffice`, `antiword`, `pandoc`.
- Отсутствие этих бинарников на чистом runner может дать red CI даже при зелёном локальном WSL pytest, если локальная машина уже имеет нужный toolchain.
- Real-document и corpus tests следует считать environment-sensitive: они должны либо работать в текущем runtime, либо явно проверять capability contract и пропускаться по нему, а не падать как будто это business-logic regression.

### Recommended Pre-Push Ritual

1. Быстрый локальный прогон в WSL через `Run Full Pytest`.
2. Отдельный parity run через VS Code task `Run Docker CI Parity Pytest`.
3. Если менялись legacy `.doc`, PDF import, corpus validation, real-document extraction или runtime normalization paths, отдельно гоняйте relevant runtime/application-flow tests и corpus selectors в том же clean environment.

### Minimal CI-Parity Checks

Предпочтительный user-visible path: `Tasks: Run Task -> Run Docker CI Parity Pytest`.

Из корня репозитория внутри WSL:

```bash
docker run --rm -v "$PWD":/src -w /src python:3.12 bash -lc '
	python -m venv /tmp/docxai-venv &&
	. /tmp/docxai-venv/bin/activate &&
	python -m pip install --upgrade pip &&
	pip install -r requirements.txt &&
	pytest tests/test_real_document_validation_corpus.py -vv -x --tb=short
'
```

Полный parity suite:

```bash
docker run --rm -v "$PWD":/src -w /src python:3.12 bash -lc '
	python -m venv /tmp/docxai-venv &&
	. /tmp/docxai-venv/bin/activate &&
	python -m pip install --upgrade pip &&
	pip install -r requirements.txt &&
	pytest tests/ -q
'
```

### Capability Probes For Upload Conversion Paths

Перед выводом, что проблема в коде, а не в runtime toolchain:

```bash
python -c "import pdfminer, docx"
command -v antiword
pandoc --version
```

Если legacy `.doc` или PDF path зависит от conversion backend, а эти команды недоступны, локальный green run в уже настроенной WSL среде не гарантирует green CI на чистом Ubuntu runner.

## Upload Normalization Contract

- `freeze_uploaded_file` и preparation path должны строиться на одном canonical normalized payload contract.
- `build_uploaded_file_token` для legacy `.doc` и `PDF` обязан сохранять source-byte-based identity; normalized DOCX bytes используются как processing payload, а не как canonical identity source.
- `document.py` не должен самостоятельно изобретать отдельный conversion path для legacy `.doc` или `PDF`; его boundary проходит через общий normalizer helper.
- Structural tier, full-tier validator и UI path должны переиспользовать один и тот же conversion contract, чтобы real-document corpus отражал реальные пользовательские upload paths.
- Любое будущее расширение форматов входа должно добавляться на этот boundary, а не в отдельные feature-specific обходные пути.
- PDF является только input format, не internal document model: запрещены parallel PDF extraction, отдельный PDF paragraph/image builder и PDF-specific ветвления в core document pipeline без новой спецификации.

## Image Modes

- `no_change` (умолчание, `image_mode_default` в `config.toml`): изображения остаются как есть; ни анализа, ни вызовов моделей.
- `safe`: консервативная доставка без semantic redraw — детерминированный PIL-шаг (автоконтраст, лёгкий контраст, цвет, резкость); анализ изображения идёт без vision-вызова, потому что safe-план его не использует. Используется и как fallback для unsafe/high-risk кейсов.
- `semantic_redraw_direct`: creative redraw по смыслу, когда analysis/policy допускают semantic route.
- `semantic_redraw_structured`: conservative structured redraw; deterministic reconstruction (сцена от vision-модели, текст рисуется локальными шрифтами) идёт первой только для таблиц, а для остальных типов — только как запасной путь, если structured edit/generate не удался.
- `compare_all`: compare-panel режим ручной проверки — до трёх вариантов рядом в финальном DOCX.

## Mode Selection Guidance

- `safe` выбирается для фотографий, скриншотов и любых кейсов, где важнее всего не потерять исходное содержание.
- `semantic_redraw_direct` выбирается для explainers, инфографики, слайдов и других визуалов, где допустим redesign композиции.
- `semantic_redraw_structured` выбирается для таблиц, схем, диаграмм и других изображений, где важнее сохранить отношения, текст и layout.
- `compare_all` выбирается, когда пользователь хочет сравнить варианты визуально в итоговом DOCX: safe-вариант всегда, креативный и структурный — только если анализ разрешил перерисовку. Семантический вариант, совпавший с safe, не вставляется повторно; выбора «лучшего» варианта нет.

## Internal Routing Notes

- Пользовательский UI mode фиксирует intent, но не заставляет pipeline нарушать safety/policy/validation ограничения.
- `safe` не запускает semantic redraw вообще; изображения с safe-профилем (`*_safe_fallback`, `mixed_or_ambiguous_fallback`) идут в safe в любом режиме.
- `semantic_redraw_direct` не обязан насильно переключаться в deterministic reconstruction только из-за структурности картинки; route определяется analysis/policy.
- `semantic_redraw_structured` остаётся generation-first/conservative режимом, при этом deterministic reconstruction допустим как внутренний delivery path без смены пользовательского mode label.
- `compare_all` готовит несколько candidate-вариантов в одном проходе и не требует отдельной финальной пересборки из compare-panel.
- Бюджет `semantic_redraw_max_model_calls_per_image` (по умолчанию 9) считает логические операции на один семантический вариант — ретраи и адаптации параметров одной операции списываются один раз — и не включает анализ исходного изображения: тот списывается только с бюджета документа. Оценка бюджета документа для `compare_all` — `2 × per_image + 1` на изображение (два семантических варианта плюс анализ).
- `preferred_strategy` в `image_prompt_registry.toml` — информационное поле: оно только логируется и маршрутизацию не определяет.

## Image Models (spec 062)

Под режимом изображений в sidebar стоят два выбора модели; оба OpenAI-only (замок провайдера в `src/docxaicorrector/core/config.py`):

- **«Модель разбора изображений»** — четыре роли, которые читают картинки: `image_analysis`, `image_validation`, `image_reconstruction`, `image_generation_vision`. Показывается только в режимах перерисовки (`semantic_redraw_direct`, `semantic_redraw_structured`, `compare_all`): в `safe` анализ идёт без модели (FR-033 спеки 062), и селектор там ничего бы не менял. Варианты — `[models.image_vision].options` в `config.toml` (`gpt-5.4-mini` по умолчанию, `gpt-6.1-sol`, `gpt-6.1-terra`).
- **«Модель рисования»** — две роли Images API: `image_generation`, `image_edit`. Показывается только в режимах, которые рисуют (`semantic_redraw_direct`, `semantic_redraw_structured`, `compare_all`). Варианты — `[models.image_draw].options` (`gpt-image-2.5-flare` по умолчанию, `gpt-image-2.5-sunburst`).

**Умолчания по режимам (решение владельца 2026-11-09).** Селекторы предвыбирают лучшую по замеру пару для режима, пользователь может выбрать другую на время прогона: `semantic_redraw_structured` — `gpt-6.1-terra` + `gpt-image-2.5-flare`; `semantic_redraw_direct` — `gpt-6.1-terra` + `gpt-image-2.5-sunburst`; `compare_all` — `gpt-6.1-terra` + `gpt-image-2.5-flare`; `safe` и `no_change` не вызывают image-моделей и селекторов не показывают. Таблица — `[models.image_vision.mode_defaults]` / `[models.image_draw.mode_defaults]` в `config.toml` (ключ — значение `ImageMode`); режим без записи берёт обычный `default`, а `DOCX_AI_IMAGE_VISION_MODEL` / `DOCX_AI_IMAGE_DRAW_MODEL` закрепляют пару для всех режимов и таблицу отключают. UI и раннер валидации берут пару одним резолвером (`src/docxaicorrector/core/config.py`, `get_image_model_choice` / `resolve_image_role_models` с `image_mode`). Основание — `D:\Temp\docxai-runs\image-compare-2026-11-07\verdicts.md`: `gpt-6.1-terra` — самый точный и единственный стабильный читатель (56/56 подписей графика, одинаковое число узлов в каждом вызове), цена анализа ≈ 0,01 USD против ≈ 0,003 у mini при ≈ 0,05–0,07 USD за вызов рисования; две причины, по которым terra проигрывал в продукте, исправлены позже (`ed7708e` — плотные/кириллические картинки больше не уходят в safe по анализу; `0289d9f` — творческий путь сохраняет тёмный текст на прозрачном фоне). flare даёт лучшую структурную перерисовку (на графике 3 неверных деления оси против 12 у sunburst), sunburst — единственный, кто не искажал кириллицу в direct-режиме. Выбор пользователя в UI живёт по ключу виджета с именем режима и сохраняется между перезапусками страницы в том же режиме.

Порядок разрешения для каждой роли, старший первым: `DOCX_AI_MODELS_IMAGE_<ROLE>_DEFAULT` → `[models.image_<role>].default` → выбор в UI или поле run-профиля `image_vision_model` / `image_draw_model` → `DOCX_AI_IMAGE_VISION_MODEL` / `DOCX_AI_IMAGE_DRAW_MODEL` → `default` секции. Закреплённая по роли модель не меняется выбором в UI; sidebar пишет об этом подписью, лог — событием `image_model_role_override_active`. «Вариант 1» спеки 062 — `gpt-5.4-mini` + `gpt-image-2.5-flare`, «вариант 2» — `gpt-6.1-sol` + `gpt-image-2.5-sunburst`; это сочетания двух выборов, а не отдельные сущности. Что ушло в прогон, видно в `runtime_config.effective.image_models`, строке `image_models=` в `run_summary.txt` и в `model_accounting_image_model_call_counts_by_role` (роль → модель → число вызовов). Параметры запроса Images API строятся по таблице возможностей `src/docxaicorrector/image/model_capabilities.py`.

## Audiobook Mode

- `processing_operation="audiobook"` является отдельным text mode наряду с `edit` и `translate`.
- Для standalone audiobook runtime принудительно коэрсит effective `image_mode` в `no_change`, даже если non-UI caller передал другое значение.
- `audiobook` — один технический проход над УЖЕ ГОТОВЫМ текстом (спека 070): он не переводит и не редактирует, поэтому у него нет пары языков и нет интенсивности редактуры (эти настройки для него не читаются), а модель берётся из `[models.audiobook].default` или из выбора в UI. Текст остаётся на своём языке; в нём нет тегов озвучки, числа и сокращения записываются словами.
- Что НЕ озвучивается, решается по каждому абзацу, а не по блоку: изображения, таблицы, подписи, оглавление, указатель, служебный аппарат, примечания в теле и обрывки без связного текста (роль, регион и ФОРМА текста, не слова). Все такие абзацы перечислены с адресами и причинами в событии `audiobook_narration_exclusions`, а число абзацев на входе, которые должны дойти до озвучки, — знаменатель проверки полноты.
- Остаток после прохода (цифры, сокращения, символы) проверяется по форме; один блок получает не больше одного вызова исправления. Абзац, который не удалось довести, остаётся в тексте с пометкой `needs_review` (событие `audiobook_needs_review` с адресами и образцами, notice на экране результата) — озвучка не теряет абзацев молча.
- Замер без платных вызовов: `scripts/measure-narration-exclusion.py --operation audiobook --per-paragraph <файл.docx>` печатает каждый исключаемый абзац с адресом и причиной. Входы замера — переведённые документы `tests/sources/translated/` (профили `audiobook-*-translated` в `corpus_registry.toml`, запуск — `ui-parity-standalone-audiobook`).
- Итоговый narration artifact пишется в `.run/ui_results/` как `<stem>.result.tts.txt` и, когда собраны, `<stem>.result.tts.docx` (DOCX для ElevenLabs Studio: `Heading 1` = глава, остальное `Normal`) и `<stem>.result.tts.pdf` (LibreOffice из этого DOCX) — рядом с `.result.md` и `.result.docx`; все файлы группы одного прогона делят один stem и чистятся вместе. Все три формата озвучки строятся из одних и тех же абзацев (спека 072).
- Для инструмента поэтапной озвучки (спека 073, решение D-4) в ту же группу пишется файл книги `<stem>.result.narration.json`: сегменты (тексты — те же, что в `.tts.txt`, побайтно; `"\n\n".join(текстов сегментов)` равно `.tts.txt`), главы, паузы по видам (`chapter`, `heading`, `scene_break`), принятые чтения сокращений словаря и сводка. Он строится независимо от DOCX и PDF: сбой любого из трёх не лишает остальных. Схема — `specs/073-narration-for-the-ear/contracts/narration-book.md`. Кнопка «Файл книги для озвучки (.json)» стоит в строке «Текст для озвучки» после TXT.
- Для `audiobook` UI показывает две строки кнопок. «Текст для озвучки»: `DOCX для ElevenLabs Studio`, `PDF` и `Текст для ElevenLabs (.txt)`; «Для проверки»: `DOCX (для инспекции)` и `Markdown (для инспекции)`. Если DOCX или PDF не собран, кнопки нет, а под строкой — причина; TXT остаётся. Превышение лимитов Studio (главы, абзацы в главе, длина абзаца) — рекомендательный notice `result.audiobook_studio_limits_exceeded`, файл не блокируется.
- Для `edit` / `translate` UI сохраняет обычные labels `Отредактированный ...` или `Переведённый ...` и не предлагает narration: второй проход над результатом редактуры и перевода удалён спекой 070.
- Markdown-разметку озвучка не разбирает: стриппер, читавший Markdown, удалён спекой 070; narration-проверка только публикует находки (`narration_artifact_review_data`: DOI, ISBN, arXiv, ссылки-цитаты) и не роняет прогон.

## Delivery Contract

- UI mode не равен автоматически внутренней стратегии генерации: delivery определяется совместно analysis, policy и validation.
- `safe` соответствует внутренней safe/fallback delivery ветке.
- `semantic_redraw_structured` может законно завершиться deterministic reconstruction delivery без смены пользовательского режима.
- `compare_all` не требует обязательной дополнительной пересборки из UI: итоговый DOCX уже может содержать доступные compare-варианты.
- Manual-review contract (`keep_all_image_variants`) может сохранять `safe` и candidate-варианты в финальном DOCX для визуальной проверки fallback decision.
- Для `compare_all` и manual-review multi-variant delivery варианты вставляются в общий side-by-side layout container без видимых label-абзацев в теле документа.
- Имена compare/manual-review вариантов сохраняются как скрытое descriptive metadata изображения (`docPr/@descr`), а не как печатный текст рядом с картинкой.

## Supporting References

- Детали WSL-first cutover: `plans/WSL_FIRST_DEV_WORKFLOW_SPEC.md`.
- Детали startup performance contract: `docs/STARTUP_PERFORMANCE_CONTRACT.md`.
- Детали cleanup тестового контракта: `plans/TEST_WORKFLOW_CONTRACT_CLEANUP_SPEC_2026-03-14.md`.
- Детали DOCX formatting hardening: `docs/archive/specs/DOCX_FORMATTING_HARDENING_SPEC_2026-03-13.md`.
- Детали PDF input normalization: `docs/archive/specs/PDF_SOURCE_IMPORT_SPEC_2026-04-26.md`.
- Исторические, superseded и point-in-time документы перечислены в `docs/ARCHIVE_INDEX.md`.
