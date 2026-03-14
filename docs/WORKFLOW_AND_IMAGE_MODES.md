# Current Workflow And Image Modes

Этот документ является единственным актуальным source of truth для двух поверхностей, которые чаще всего drift-ят при локальных изменениях:

- dev/runtime workflow;
- пользовательские image modes и их фактический delivery contract.

Если другой markdown-документ в `docs/` формулирует эти контракты иначе, приоритет всегда у этого файла. Historical, point-in-time и superseded материалы перечислены в `docs/ARCHIVE_INDEX.md`.

## Runtime Workflow

- Единственный runtime для Python, pytest, Streamlit и Pandoc: WSL `.venv`.
- Windows PowerShell используется только как thin wrapper и transport layer для scripts/ и VS Code tasks.
- Каталог `.venv-win/` допустим только для editor tooling и статического анализа; он не должен участвовать в runtime auto-selection.
- Официальные entry points для запуска и диагностики: `Project Status`, `Start Project`, `Stop Project`, `Run Full Pytest WSL`, `Run Current Test File WSL`, `Run Current Test Node WSL`, `Tail Streamlit Log`.
- Официальные PowerShell wrappers: `scripts/start-project.ps1`, `scripts/stop-project.ps1`, `scripts/status-project.ps1`, `scripts/run-tests.ps1`, `scripts/run-test-file.ps1`, `scripts/run-test-node.ps1`, `scripts/tail-streamlit-log.ps1`.
- Вся command logic живёт в `scripts/project-control-wsl.sh`; wrappers и tasks не должны дублировать raw pytest или streamlit command chains.

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

## Supporting References

- Детали WSL-first cutover: `plans/WSL_FIRST_DEV_WORKFLOW_SPEC.md`.
- Детали DOCX formatting hardening: `docs/DOCX_FORMATTING_HARDENING_SPEC_2026-03-13.md`.
- Исторические, superseded и point-in-time документы перечислены в `docs/ARCHIVE_INDEX.md`.