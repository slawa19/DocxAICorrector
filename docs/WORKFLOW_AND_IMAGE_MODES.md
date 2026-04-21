# Current Workflow And Image Modes

Этот документ является единственным актуальным source of truth для двух поверхностей, которые чаще всего drift-ят при локальных изменениях:

- dev/runtime workflow;
- пользовательские image modes и их фактический delivery contract.

Если другой markdown-документ в `docs/` формулирует эти контракты иначе, приоритет всегда у этого файла. Historical, point-in-time и superseded материалы перечислены в `docs/ARCHIVE_INDEX.md`.

## Runtime Workflow

- Единственный runtime для Python, pytest, Streamlit и Pandoc: WSL `.venv`.
- Windows PowerShell используется только как thin wrapper и transport layer для lifecycle/diagnostic scripts и соответствующих VS Code tasks.
- Каталог `.venv-win/` допустим только для editor tooling и статического анализа; он не должен участвовать в runtime auto-selection.
- Upload contract больше не DOCX-only: пользовательский вход может быть `.docx` или legacy `.doc`; после boundary в `processing_runtime.py` downstream-слои обязаны работать с normalized DOCX bytes, но для legacy `.doc` token identity остаётся привязанной к исходным source bytes.
- Предпочтительный backend автоконвертации legacy `.doc` внутри WSL: `LibreOffice` / `soffice`; fallback backend: `antiword` + `pandoc`.
- Официальные entry points для запуска и диагностики: `Project Status`, `Start Project`, `Stop Project`, `Run Full Pytest`, `Run Current Test File`, `Run Current Test Node`, `Tail Streamlit Log`.
- Официальные видимые real-document entry points: `Run Lietaer Real Validation`, `Run Real Document Validation Profile`, `Run Real Document Quality Gate`.
- Полный `Run Full Pytest` не должен неявно запускать дорогой real-document AI smoke только потому, что в `.env` присутствует `OPENAI_API_KEY`; для такого smoke требуется явный opt-in.
- Официальный тестовый entry point: `bash scripts/test.sh ...` из WSL или VS Code tasks, которые вызывают WSL/bash напрямую.
- Для agent-side debug запусков pytest должен выполняться по одному selector за команду; нельзя склеивать несколько прогонов через `&&` или уводить их в hidden/background terminal, если нужен полный и наблюдаемый результат.
- Официальные PowerShell wrappers: `scripts/start-project.ps1`, `scripts/stop-project.ps1`, `scripts/status-project.ps1`, `scripts/tail-streamlit-log.ps1`.
- Вся command logic живёт в `scripts/project-control-wsl.sh` и `scripts/test.sh`; lifecycle wrappers и tasks не должны дублировать raw streamlit or pytest command chains.

## CI Parity Debugging Contract

- Локальный WSL `.venv` остаётся source of truth для обычной разработки, но сам по себе не доказывает CI-совместимость.
- Для расследования CI-only regressions нужен отдельный clean-environment parity run на Python 3.12, потому что CI job `tests` выполняется именно на таком runtime.
- Для багов вокруг legacy `.doc`, corpus validation и real-document extraction проверяйте не только Python packages, но и системные бинарники: `soffice`, `antiword`, `pandoc`.
- Отсутствие этих бинарников на чистом runner может дать red CI даже при зелёном локальном WSL pytest, если локальная машина уже имеет нужный toolchain.
- Real-document и corpus tests следует считать environment-sensitive: они должны либо работать в текущем runtime, либо явно проверять capability contract и пропускаться по нему, а не падать как будто это business-logic regression.

### Recommended Pre-Push Ritual

1. Быстрый локальный прогон в WSL через `Run Full Pytest`.
2. Отдельный parity run через VS Code task `Run Docker CI Parity Pytest`.
3. Если менялись legacy `.doc`, corpus validation, real-document extraction или runtime normalization paths, отдельно гоняйте `tests/test_real_document_validation_corpus.py` в том же clean environment.

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

### Capability Probes For Legacy DOC Paths

Перед выводом, что проблема в коде, а не в runtime toolchain:

```bash
command -v soffice || command -v libreoffice
command -v antiword
pandoc --version
```

Если legacy `.doc` path зависит от conversion backend, а эти команды недоступны, локальный green run в уже настроенной WSL среде не гарантирует green CI на чистом Ubuntu runner.

## Upload Normalization Contract

- `freeze_uploaded_file` и preparation path должны строиться на одном canonical normalized payload contract.
- `build_uploaded_file_token` для legacy `.doc` обязан сохранять source-byte-based identity; normalized DOCX bytes используются как processing payload, а не как canonical identity source.
- `document.py` не должен самостоятельно изобретать отдельный conversion path для legacy `.doc`; его boundary проходит через общий normalizer helper.
- Structural tier, full-tier validator и UI path должны переиспользовать один и тот же conversion contract, чтобы real-document corpus отражал реальные пользовательские upload paths.
- Любое будущее расширение форматов входа должно добавляться на этот boundary, а не в отдельные feature-specific обходные пути.

## Image Modes

- `safe`: консервативная доставка без semantic redraw; используется как fallback для unsafe/high-risk кейсов.
- `semantic_redraw_direct`: creative redraw по смыслу, когда analysis/policy допускают semantic route.
- `semantic_redraw_structured`: conservative structured redraw; для части diagram/infographic кейсов может доставляться через deterministic reconstruction.
- `compare_all`: compare-panel режим ручной проверки, где pipeline может сохранить несколько вариантов в финальном DOCX.

## Mode Selection Guidance

- `safe` выбирается для фотографий, скриншотов и любых кейсов, где важнее всего не потерять исходное содержание.
- `semantic_redraw_direct` выбирается для explainers, инфографики, слайдов и других визуалов, где допустим redesign композиции.
- `semantic_redraw_structured` выбирается для таблиц, схем, диаграмм и других изображений, где важнее сохранить отношения, текст и layout.
- `compare_all` выбирается, когда пользователь хочет получить safe/direct/structured варианты сразу и сравнить их визуально в итоговом DOCX.

## Internal Routing Notes

- Пользовательский UI mode фиксирует intent, но не заставляет pipeline нарушать safety/policy/validation ограничения.
- `safe` не запускает semantic redraw вообще.
- `semantic_redraw_direct` не обязан насильно переключаться в deterministic reconstruction только из-за структурности картинки; route определяется analysis/policy.
- `semantic_redraw_structured` остаётся generation-first/conservative режимом, при этом deterministic reconstruction допустим как внутренний delivery path без смены пользовательского mode label.
- `compare_all` готовит несколько candidate-вариантов в одном проходе и не требует отдельной финальной пересборки из compare-panel.

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
- Детали DOCX formatting hardening: `docs/DOCX_FORMATTING_HARDENING_SPEC_2026-03-13.md`.
- Исторические, superseded и point-in-time документы перечислены в `docs/ARCHIVE_INDEX.md`.