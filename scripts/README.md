# scripts/

Что лежит в этом каталоге, кто на это опирается и когда что запускать. Таблица собрана 2026-11-07
по `git grep` всего репозитория (без `docs/archive`); источник правды — сами скрипты и ссылки на
них, а не этот файл. Добавляя скрипт, впишите его в одну из четырёх групп.

Все Python- и shell-скрипты запускаются в WSL Debian (см. `AGENTS.md`, Runtime Contract); из
Windows-shell — через `wsl.exe -d Debian --cd "<корень checkout>" -- bash ...`. Измерительные
Python-скрипты ждут `. .venv/bin/activate && export PYTHONPATH="$PWD/src:$PWD"`, если в их
docstring не сказано иное.

## 1. Контракт — на них опираются тесты, CI, VS Code tasks или `AGENTS.md`

Менять только вместе с теми, кто на них ссылается.

| Скрипт | Назначение | Кто опирается |
| --- | --- | --- |
| `test.sh` | Канонический pytest-раннер (selector до опций) | CI, tasks `Run Full Pytest` / `Current Test File` / `Current Test Node`, `AGENTS.md` |
| `docker-ci-parity.sh` | Повтор `ci.yml` в контейнере `python:3.12`, не трогая рабочее дерево | task `Run Docker CI Parity Pytest`, `AGENTS.md`, `tests/test_script_contract_static.py` |
| `setup-wsl.sh` | Bootstrap WSL runtime: apt-пакеты, `.venv`, зависимости | `README.md`, `AGENTS.md`, `tests/test_dependency_consistency.py` |
| `run-real-document-validation.sh` | Real-document validation профиль (`run_lietaer_validation.py`) | tasks `Run Lietaer Real Validation`, `Run Lietaer Real Validation AI`, `Run Lietaer Full Benchmark Validation`, `Run Real Document Validation Profile`; `AGENTS.md`, `README.md` |
| `run-real-document-quality-gate.sh` | Opt-in quality gate: corpus-тест с обязательными capabilities | task `Run Real Document Quality Gate`, `AGENTS.md`, конституция |
| `run-structural-preparation-diagnostic.sh` | Структурный snapshot подготовки по профилю; генерация заглушена (passthrough), текст модель не пишет | tasks `Run Structural Preparation Diagnostic`, `Run Structure Recovery Diagnostic (First 20 Pages)`; `AGENTS.md`, `tests/test_script_contract_static.py` |
| `project-control-wsl.sh` | WSL-сторона lifecycle: start/stop/status/setup/логи Streamlit | вызывается из `_shared.ps1`; `tests/test_script_workflow_smoke.py` |
| `_shared.ps1` | Общие функции PowerShell-обёрток | все `*-project.ps1` |
| `setup-project.ps1` | Обёртка: установка зависимостей через WSL | task `Setup Project` |
| `start-project.ps1` | Обёртка: запуск Streamlit в WSL | task `Start Project` |
| `stop-project.ps1` | Обёртка: остановка управляемого экземпляра | task `Stop Project` |
| `restart-project.ps1` | Обёртка: stop + start | task `Restart Project` |
| `status-project.ps1` | Обёртка: статус runtime и окружения | task `Project Status` |
| `tail-streamlit-log.ps1` | Обёртка: хвост `streamlit.log` | task `Tail Streamlit Log` |
| `.PSScriptAnalyzerSettings.psd1` | Подавление `PSUseDeclaredVarsMoreThanAssignments` для dot-source переменных `_shared.ps1` | нигде не подключён автоматически; PSScriptAnalyzer читает его только с `-Settings` |
| `classify-formatting-residuals.py` | Офлайн-классификация formatting-residuals из готового JSON-отчёта | запускается `tests/test_validation_formatting_replay.py` |
| `run-reader-cleanup-lineage-rebuild-harness.py` | Офлайн-сборка lineage/rebuild reader-cleanup из сохранённых артефактов | запускается `tests/test_document_pipeline.py` |
| `run-reader-cleanup-structural-matrix.py` | Структурная replay-матрица reader-cleanup (исследовательский прогон) | загружается `tests/test_reader_cleanup_structural_matrix.py` |

## 2. Evidence — источник чисел в спеках; должны оставаться запускаемыми

Удалять нельзя: без них число в спеке нельзя перепроверить (Конституция VIII). Все офлайн, без LLM,
кроме явно помеченных.

| Скрипт | Что мерит | Чьи числа |
| --- | --- | --- |
| `run-reader-cleanup-faithful-replay.py` | Офлайн-replay трёх записанных прогонов reader-cleanup; `--live` — платный прогон через провайдер | спека 052, `docs/WHERE_WE_ARE.md`, `tests/test_replay_baseline_consistency.py` |
| `measure-reader-cleanup-visible-defects.py` | Видимые читателю дефекты книги до/после reader-cleanup | `docs/WHERE_WE_ARE.md` (первый live-прогон 2026-08-02) |
| `measure-narration-exclusion.py` | Что реально исключает решение narration-include, по причинам | спека 054 |
| `probe-bibliography-tail.py` | Где якорится и докуда тянется исключение reference-region в audiobook | спека 054 |
| `measure-pdf-bridge-signal-carry.py` | Перепись моста PDF→DOCX: что измерил импортёр и что дошло до DOCX | спека 055 (коммиты `0a91400`, `3472958`; в тексте спеки путь не назван) |
| `measure-pdf-bridge-revived-rules.py` | Срабатывания трёх «мёртвых» правил до/после переноса сигналов | спека 055 (те же коммиты) |
| `measure-pdf-image-frames.py` | Мост PDF→DOCX с заменой картинок отрисовкой рамки и без неё: абзацы (текст, стиль) и sha1/размер картинок по порядку, время; для каждой замены — PNG «было / стало / страница» (`--out`) | спека 082 срез A (`tasks.md` T013, `research.md` R20) |
| `measure-translation-signal.py` | Что отличает переведённый абзац от непереведённого, на записанных прогонах | спека 059 |
| `measure-block-pair-rule.py` | Правило пары (текст = источник) на гранулярности блока | спека 059, `tests/test_spec_059_translation_completeness.py` |
| `measure-glossary-candidates.py` | Кандидаты глоссария прогона продуктовым извлекателем (подготовка без модели или дамп абзацев) и полнота против терминологии рецензента; `--live` — ОДИН платный вызов извлечения с печатью токенов и стоимости | спека 063 P2 (`research.md` R3/R5, `tasks.md` T018–T019) |
| `measure-glossary-consistency.py` | Следует ли перевод глоссарию: по каждому термину — пары с термином в источнике и доля с закреплённой передачей (`python3 -I`, без импорта репозитория). Как измеритель SC-006 заменён `measure-glossary-adherence.py` | спека 063 P2 / SC-006 (`tasks.md` T020), `tests/test_glossary_pass.py` |
| `measure-glossary-adherence.py` | Форменная метрика следования глоссарию для читателя: только проза тела, без policy-kept/fallback и вхождений, оставленных латиницей; в заголовке — имена и многословные/дефисные/заглавные/с заметкой записи (регистрозависимо для заглавных), одиночные строчные слова отдельно; доминирующая передача ≥ 90 % при ≥ 5 вхождениях; охват секции промпта; контрастные пары (FR-004); список пар для чтения вреда (`python3 -I`, без импорта репозитория) | спека 065 FR-010 / FR-004, `tests/test_glossary_adherence_metric.py` |

## 3. Инструменты оператора — описаны в документации, запускаются руками

| Скрипт | Назначение | Где описан |
| --- | --- | --- |
| `clean-stale-run-artifacts.sh` | Чистка разовых файлов в `.run/` (по умолчанию dry-run, `--apply` удаляет) | `README.md`, `docs/LOGGING_AND_ARTIFACT_RETENTION.md` |
| `_run_cleanup_now.py` | Разовое применение retention-политик ко всем семействам `.run/` | `README.md`; bootstrap закреплён в `tests/test_script_contract_static.py` |
| `_list_log_events.py` | Перечень event-имён `log_event`/`log_exception` в коде | `docs/LOGGING_AND_ARTIFACT_RETENTION.md`; список целей проверяется `tests/test_script_contract_static.py` |
| `run_pic1_modes.py` | Живой прогон image-режимов на `tests/pic1_lietaer.jpg` (**тратит API**) | bootstrap закреплён в `tests/test_script_contract_static.py` |

## 4. Без внешних ссылок — оставлены осознанно

Ни один документ вне `docs/archive` их не называет. Оставлены, потому что работают на текущем коде
и их работу больше ничто не делает.

| Скрипт | Назначение | Почему оставлен |
| --- | --- | --- |
| `analyze_pyright.py` | Сводка `pyright --outputjson` по файлам и категориям: `pyright --outputjson \| python3 scripts/analyze_pyright.py` | `tests/test_typecheck.py` только сравнивает число ошибок с baseline и не группирует их |
| `run-pdf-import-backend-comparison.sh` | WSL-обёртка над `tools/compare_pdf_import_backends.py` (LibreOffice против text-layer моста) | инструмент покрыт `tests/test_pdf_import_backend_comparison.py`; обёртка — единственная точка запуска с `.venv` |
| `run-pdf-text-layer-quality-probe.sh` | WSL-обёртка над `tools/pdf_text_layer_quality_probe.py` | инструмент покрыт `tests/test_pdf_text_layer_quality.py` |

## Когда что запускать

- **Поднять/остановить приложение** — VS Code tasks или обёртки `start-project.ps1`,
  `stop-project.ps1`, `restart-project.ps1`, `status-project.ps1`, `tail-streamlit-log.ps1`,
  `setup-project.ps1`. Первый запуск на новой машине — `bash scripts/setup-wsl.sh` внутри WSL.
- **Тесты** — только `bash scripts/test.sh <selector> [опции]` через WSL. Перед утверждением о
  CI — `docker-ci-parity.sh` на чистом checkout.
- **Реальные документы** — `run-real-document-validation.sh` (профиль задают `DOCXAI_REAL_DOCUMENT_PROFILE` и `DOCXAI_REAL_DOCUMENT_RUN_PROFILE`; полный прогон книги тратит API — это milestone, а не шаг отладки),
  `run-real-document-quality-gate.sh` (opt-in gate), `run-structural-preparation-diagnostic.sh`
  (структура без LLM). Подробности — `docs/RUNNING_THE_PIPELINE.md`.
- **Исследования и измерения** — группа 2: перезапуск нужен, когда меняется код, на который
  опирается число в спеке; запуск и аргументы — в docstring каждого скрипта. Новый измерительный
  скрипт кладите сюда и называйте его путём в спеке, чьи числа он даёт.
- **Обслуживание `.run/`** — `clean-stale-run-artifacts.sh` (сначала без `--apply`),
  `_run_cleanup_now.py`.
