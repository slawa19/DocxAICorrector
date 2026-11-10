# Codex Review — spec 072 before the plan (2026-11-10)

- **Date:** 2026-11-10
- **Reviewed:** `specs/072-narration-docx-pdf/spec.md` on `main` @ `2e5e8d5` (draft), before any plan or code
- **Reviewer:** Codex `gpt-6-astra`, `codex exec --sandbox read-only`; 185 033 tokens
- **Scope:** every claim of «Что есть сейчас» checked against the code; feasibility of each requirement; the ElevenLabs research data and the FR-009 archive of spec 070
- **Status:** verdict «СТРОИТЬ ПОСЛЕ ПРАВОК»; 3 P1 + 6 P2 — all verified by the orchestrator and landed in the spec (Changelog 2026-11-10)
- **Canonical source of truth:** `specs/072-narration-docx-pdf/spec.md` and the code; this report is not (see `docs/reviews/README.md`)

## Поднято / вердикт / приземление

| # | Находка | Вердикт оркестратора | Приземление |
|---|---|---|---|
| 1 (P1) | Сбой DOCX → выдать TXT против «нет группы TXT без DOCX» | ПОДТВЕРЖДЕНО (Anti-regression 3 и 6 спеки) | FR-007: состав группы по собранному, гарантия `_atomic_write_group`; Non-goal об абсолютной атомарности |
| 2 (P1) | Запрет переноса строки внутри абзаца несовместим с дословностью | ПОДТВЕРЖДЕНО (`tests/test_narration_cleanup.py:205-207`) | FR-004: одиночный `\n` — разрыв строки внутри абзаца |
| 3 (P1) | Обещание «нет оглавления и подписей» против Non-goals | ПОДТВЕРЖДЕНО | US1 сужена до исключённого правилом 070 |
| 4 (P2) | Проба на рабочем столе реализует другую политику заголовков; случаи слияния не определены | ПОДТВЕРЖДЕНО (RM начинается `2 → 1`) | FR-003 (а)–(в): ранг уровней, серия, примеры; проба названа не доказательством |
| 5 (P2) | Новые байты не дойдут до экрана (список ключей состояния) | ПОДТВЕРЖДЕНО (`processing/processing_runtime.py:164-176`) | FR-008 — доставка, очистка, старый bundle; SC-007 |
| 6 (P2) | LibreOffice без изоляции профиля, тайм-аута, Stop | ПОДТВЕРЖДЕНО (лимит двух процессов, `:127`) | FR-005, SC-005, SC-006 |
| 7 (P2) | SC-003 не проверяет закладки, шрифты, кратность; CI без LibreOffice | ПОДТВЕРЖДЕНО (`ci.yml:76`, `:92`) | SC-003 переписан; тест с отметкой системной зависимости |
| 8 (P2) | Архив не воспроизводит записи; «23» не замер | ПОДТВЕРЖДЕНО | SC-001 на синтетическом наборе; «23» — прогноз; FR-011 — прогон полной Money |
| 9 (P2) | Лимиты: глава до первого H1, без заголовков, границы | ПОДТВЕРЖДЕНО | FR-006 переписан |

## Промпт

```text
Ты работаешь в том же окружении, что и оператор: читай любые файлы по абсолютным путям, включая исключённые из git, считай сам — Python и git у тебя есть. WSL тебе закрыт, поэтому наши тесты и пайплайн ты не запустишь. НЕ ВЫДУМЫВАЙ измерений; число, которого нет в файлах, называй прогнозом и говори, чем его проверить. Ничего не меняй в файлах.

Задача: проверка корректности и полноты СПЕКИ до плана и до кода. Репозиторий D:\Work\Projects\DocxAICorrector, ветка main (HEAD — выполни git -C D:\Work\Projects\DocxAICorrector log --oneline -3). Спека: D:\Work\Projects\DocxAICorrector\specs\072-narration-docx-pdf\spec.md (+ checklists\requirements.md). Правила: AGENTS.md, .specify\memory\constitution.md (III — уровни работ, VII — правила по форме без словарей и литералов книг, VIII — свежесть доказательств, Spec Format Contract).

Суть: режим аудиокниги (спека 070, D:\Work\Projects\DocxAICorrector\specs\070-audiobook-technical-pass\spec.md) сейчас выдаёт текст для озвучки только как .tts.txt; ElevenLabs Studio его не принимает (только EPUB/PDF/DOCX). Спека 072 добавляет .tts.docx (главы — Heading 1, только озвучиваемый текст, из тех же записей сборки) и .tts.pdf (из DOCX через LibreOffice).

Проверь по коду каждое утверждение раздела «Что есть сейчас» (file:line) и реалистичность требований. Поверхности (пути от D:\Work\Projects\DocxAICorrector\src\docxaicorrector\): runtime\artifacts.py (write_ui_result_artifacts, _atomic_write_group), runtime\artifact_retention.py, pipeline\narration_postprocess.py (assemble_narration_records, _build_narration_text), pipeline\audiobook_pass.py (NarrationParagraphRecord, finalize_audiobook_block, rebuild_block_with_narration_texts, _with_source_heading_prefix), pipeline\late_phases.py (где строится narration_text, вызывается write_ui_result_artifacts и пишется ui_audiobook_artifact_saved; где строится DOCX результата), generation\_generation.py (convert_markdown_to_docx_bytes, _build_reference_docx), processing\processing_runtime.py (soffice: _convert_legacy_doc_with_soffice, _convert_pdf_to_docx, _convert_legacy_doc_to_docx), ui\_ui.py (экран результата, кнопки скачивания, _build_narration_filename), ui\_app.py / processing\processing_service.py (как bundle результата несёт narration_text до экрана), tests\artifacts\real_document_pipeline\run_lietaer_validation.py (раннер: что он сохраняет в каталог прогона), docs\LOGGING_AND_ARTIFACT_RETENTION.md, AGENTS.md раздел «UI result artifacts».
Данные: исследование ElevenLabs D:\Temp\docxai-research\elevenlabs-studio\RESEARCH.md и raw\ (studio.md:703-705, :981; changelog.md:105); вывод прошлого платного прогона полной книги D:\Temp\docxai-research\070-fr009\runs\archive\20261110T074147Z_40074_money_full_standard_translated_ru\ (.tts.txt, report.json, .docx); скрипт уровней заголовков D:\Temp\docxai-research\elevenlabs-studio\heading_levels.py; пробные файлы, собранные вручную: C:\Users\RedOutPC\Desktop\Аудиокнига 070 — тексты для ElevenLabs\Проба ElevenLabs Studio\ (B — чистый DOCX, две главы.docx) и скрипт D:\Temp\docxai-research\elevenlabs-studio\build_probe_docx.py.

Что проверить:
1. Верны ли ссылки и утверждения «Что есть сейчас»; чего спека не видит (другие места, где пишется или читается группа результата, где bundle несёт текст озвучки до UI, история результатов, повторная загрузка результата, CLI/раннер).
2. FR-001/FR-002: реально ли получить уровень заголовка в записи озвучки из одного места без второго пути сборки; как детерминированные склейки и роли соотносятся с заголовками; что с абзацами, озвучиваемыми из исходника (needs_review, source_fallback).
3. FR-003: правило отображения уровней и слияния подряд идущих заголовков — корректно ли, нет ли случаев, где слияние склеит то, что не должно (заголовок главы + подзаголовок другого уровня, заголовок в конце книги), согласуется ли с SC-001 (равенство с .tts.txt); правило по форме, не по словам (VII).
4. FR-004: как гарантировать дословный текст (Pandoc интерпретирует Markdown; python-docx — нет); какой путь сборки DOCX ты бы выбрал и почему, со ссылками на код.
5. FR-005: LibreOffice в фоне в веб-процессе Streamlit — блокировки, параллельные профили soffice, время на полной книге (прогноз), шрифты с кириллицей в WSL (проверь system-requirements.apt, scripts\setup-wsl.sh), закладки PDF; что делать в CI (Docker-образ — Dockerfile/ci.yml, есть ли там LibreOffice).
6. FR-007/FR-008: атомарность группы (spec 023), хранение/чистка, обратная совместимость чтения старых групп, имена файлов при скачивании, UI-раскладка (AGENTS.md Streamlit Layout Contract).
7. SC: измеримы ли; не вакуумны ли; что из них можно проверить без платного прогона.
8. Non-goals / Anti-regression: чего не хватает; есть ли лишнее.
9. Уровень работы (полный цикл) — оправдан ли.

Требования к ответу: на каждую находку — file:line (находка без пути не считается); серьёзность P1 (спека приведёт к порче/потере текста, нарушению контракта, невыполнимому требованию) / P2 / P3; уверенность. Возражение с конкретной ссылкой ценнее согласия. Ответ по-русски. Последней строкой — вердикт ровно одним из: СТРОИТЬ / СТРОИТЬ ПОСЛЕ ПРАВОК / НЕ СТРОИТЬ.
```

## Ответ Codex (финальный отчёт)

Проверено на `main`, HEAD совпадает с указанной спекой.

```text
2e5e8d5 spec 072: narration text as DOCX and PDF next to the .tts.txt (draft)
be6e6a2 spec 070: closed by the owner; number substitution is an accepted edge case
f225bc4 spec 071: Codex acceptance review report, Changelogs, close 071
```

Файлы не изменялись. WSL, тесты и пайплайн не запускались. Пересчёт сохранённых данных выполнен через PowerShell/.NET, включая чтение XML внутри DOCX. Доступные Windows Python-launcher и `.venv-win` оказались неработоспособны.

## Находки

### 1. P1 · Высокая уверенность — взаимоисключающие требования к отказу DOCX и атомарности

Anti-regression 3 требует выдать TXT при сбое сборки DOCX. Anti-regression 6 запрещает группу с TXT без DOCX. Оба условия одновременно выполнить невозможно. Также существующий `_atomic_write_group` прямо описывает остаточное окно частичной публикации при аварийном завершении процесса между `os.replace`.

Нужно определить состав группы по успешно подготовленным форматам. Ошибка конвертации допускает отсутствие соответствующего формата и сопровождается уведомлением. Атомарная публикация применяется к выбранному составу с существующей гарантией отката при обрабатываемой ошибке. Абсолютное обещание отсутствия частичных групп при любом падении потребовало бы другого контракта хранения. [spec.md:156](specs/072-narration-docx-pdf/spec.md:156), [spec.md:162](specs/072-narration-docx-pdf/spec.md:162), [artifacts.py:192](src/docxaicorrector/runtime/artifacts.py:192).

### 2. P1 · Высокая уверенность — запрет внутренних переносов несовместим с дословностью

FR-004 запрещает перевод строки внутри абзаца. Действующий cleanup сохраняет одиночные переводы строк. Это явно закреплено тестами с результатами `"а б\nв"` и `"а\nб"`. Сборщик TXT также сохраняет их внутри текста записи.

Для такого поддерживаемого входа возможны три результата. Сохранение переноса нарушает FR-004. Замена пробелом нарушает SC-001, который разрешает только слияния заголовков. Изменение TXT нарушает SC-004.

Нужно выбрать и записать допустимую нормализацию для DOCX либо разрешить внутренние переносы. В проверенной полной книге таких абзацев **0**, поэтому проверка только на ней этот конфликт пропустит. [spec.md:105](specs/072-narration-docx-pdf/spec.md:105), [spec.md:126](specs/072-narration-docx-pdf/spec.md:126), [test_narration_cleanup.py:205](tests/test_narration_cleanup.py:205), [narration_postprocess.py:169](src/docxaicorrector/pipeline/narration_postprocess.py:169).

### 3. P1 · Высокая уверенность — сценарий обещает очистку, которую scope запрещает выполнять

User Story 1 и её третий сценарий обещают отсутствие оглавления, подписей и примечаний вообще. При этом SC-002 требует сохранить пять нераспознанных строк оглавления, а Non-goals исключает исправление их распознавания. Спека 070 также документирует звучащие подписи без роли и строку библиографии внутри текста.

Следует ограничить обещание **абзацами, исключёнными действующим правилом 070**. Нераспознанные элементы и остатки `needs_review` сохраняются вместе с остальным TXT. Иначе реализация будет вынуждена нарушить либо равенство текста, либо границы задачи. [spec.md:62](specs/072-narration-docx-pdf/spec.md:62), [spec.md:128](specs/072-narration-docx-pdf/spec.md:128), [spec.md:148](specs/072-narration-docx-pdf/spec.md:148), [070/spec.md:330](specs/070-audiobook-technical-pass/spec.md:330).

### 4. P2 · Высокая уверенность — пробный DOCX реализует другую политику заголовков

В сохранённом результате RM начало имеет уровни **2 → 1**. FR-003 оставит два абзаца, сначала `Heading 2`, затем `Heading 1`. Пробный генератор объединяет **все начальные заголовки независимо от уровня**, а все последующие превращает в `Heading 2`. Он также добавляет два вступительных абзаца вне записей озвучки.

Я прочитал пробный DOCX. В нём 198 абзацев, два `Heading 1` и четырнадцать `Heading 2`. Его успешная загрузка подтвердит именно эту структуру. Переносить результат такой пробы на FR-003 нельзя без дополнительной проверки. [Rethinking_Money_ch3_translated.md:3](tests/artifacts/real_document_pipeline/runs/20261110T080357Z_41448_rm_ch3_translated_ru/Rethinking_Money_ch3_translated.md:3), [build_probe_docx.py:62](/D:/Temp/docxai-research/elevenlabs-studio/build_probe_docx.py:62), [build_probe_docx.py:66](/D:/Temp/docxai-research/elevenlabs-studio/build_probe_docx.py:66).

В FR-003 нужно дополнительно закрепить следующие случаи.

- `H1 → H2 → H1` сохраняет три заголовка. Заголовок другого уровня прерывает серию.
- Одиночный заголовок в конце сохраняется. Общее обещание устранить пустые главы здесь невыполнимо.
- Два заголовка, ставшие соседними после исключения всего содержимого между ними, могут принадлежать разным разделам. Нужно явно принять такое слияние либо учитывать структурную границу.
- Для уровней `{2, 4}` нужно выбрать отображение второго уровня в `Heading 2` или `Heading 3`.
- Минимальный уровень документа может обозначать часть или название книги. Сам по себе он не гарантирует выделение всех семантических глав.

Все эти решения можно выразить через роли, уровни и границы. Словари названий не нужны. [spec.md:101](specs/072-narration-docx-pdf/spec.md:101), [constitution.md:191](.specify/memory/constitution.md:191).

### 5. P2 · Высокая уверенность — FR-007/008 пропускают обязательный контракт доставки до экрана

Сохранение файлов и добавление кнопок ещё не доставят новые форматы пользователю. Между worker и UI находится allowlist состояния, который **отбрасывает неизвестные ключи**. Затем результат проходит через `get_current_result_bundle`, `build_result_bundle` и `_render_completed_result_view`. Сейчас эта цепочка несёт только основной DOCX и `narration_text`.

В спеке нужны проверяемые требования к передаче новых байтов, доступности форматов и уведомлений через всю цепочку. Особенно важны повторная отрисовка, следующий запуск, отмена и старый bundle без новых полей. Иначе возможны отсутствующие кнопки или скачивание файла предыдущего запуска. [processing_runtime.py:164](src/docxaicorrector/processing/processing_runtime.py:164), [processing_runtime.py:1850](src/docxaicorrector/processing/processing_runtime.py:1850), [processing_runtime.py:1689](src/docxaicorrector/processing/processing_runtime.py:1689), [state.py:734](src/docxaicorrector/runtime/state.py:734), [_app.py:904](src/docxaicorrector/ui/_app.py:904).

**Историю результатов с загрузкой `.run/ui_results` в UI в проверенной цепочке не обнаружил.** Текущий экран строится из session state. `.run/completed_*` хранит исходник для reuse/restart. Создавать историю в рамках 072 оснований нет. Совместимость нужна для старых bundle и существующих сохранённых групп. Отдельный segment registry уже сохраняет `result_artifact_paths` целиком. [AGENTS.md:461](AGENTS.md:461), [processing_runtime.py:1778](src/docxaicorrector/processing/processing_runtime.py:1778), [reassembly.py:163](src/docxaicorrector/pipeline/reassembly.py:163).

### 6. P2 · Высокая уверенность — «LibreOffice в фоне» не определяет изоляцию и завершение операции

Приложение допускает два одновременно работающих processing worker по умолчанию. Текущие вызовы soffice используют отдельные временные каталоги файлов, но не задают отдельный профиль LibreOffice. Общий поиск бинаря эту проблему не решает.

FR-005 должен потребовать изоляцию профиля каждой конвертации, ограниченное ожидание, завершение принадлежащего операции процесса при тайм-ауте, очистку временных файлов и проверку реально созданного непустого PDF. Следует определить поведение Stop. Существующий `_run_completed_process` уже содержит тайм-аут и завершение группы процессов, но во время `communicate` Stop не проверяет. [spec.md:108](specs/072-narration-docx-pdf/spec.md:108), [processing_runtime.py:126](src/docxaicorrector/processing/processing_runtime.py:126), [processing_runtime.py:415](src/docxaicorrector/processing/processing_runtime.py:415), [processing_runtime.py:321](src/docxaicorrector/processing/processing_runtime.py:321).

Конвертацию разумно выполнять в существующем background worker. `--headless` задаёт работу без интерфейса. Отдельный профиль задаётся через `-env:UserInstallation=...`. [processing_runtime.py:2150](src/docxaicorrector/processing/processing_runtime.py:2150), [официальные параметры LibreOffice](https://help.libreoffice.org/latest/en-US/text/shared/guide/start_parameters.html).

**Прогноз времени** для текстовой книги такого объёма — секунды или десятки секунд, при холодном запуске и конкуренции возможны минуты. Замера экспорта в предоставленных данных нет. Проверять следует на полном `.tts.docx` в WSL, отдельно холодный запуск, повторный запуск и две параллельные конвертации. Имеющиеся 120 секунд относятся к импортному helper и сами по себе не доказывают подходящий бюджет экспорта. [processing_runtime.py:83](src/docxaicorrector/processing/processing_runtime.py:83).

### 7. P2 · Высокая уверенность — SC-003 не проверяет часть обязательных свойств PDF

Извлечение текста не доказывает наличие закладок или встраивание шрифтов. Проверка «содержит каждый абзац» допускает лишний текст и дублирование. Без условия непустого ожидаемого содержимого она допускает вакуумное прохождение.

Нужны отдельные проверки порядка и кратности текста, дерева закладок и встроенных шрифтов. Нормализацию переносов следует определить точно, сохранив различимость букв, пунктуации и повторов. LibreOffice документирует `ExportBookmarks`, но наличие этого параметра не заменяет проверку результата. [spec.md:130](specs/072-narration-docx-pdf/spec.md:130), [spec.md:168](specs/072-narration-docx-pdf/spec.md:168), [официальные параметры PDF](https://help.libreoffice.org/latest/en-US/text/shared/guide/pdf_params.html).

В `system-requirements.apt` LibreOffice присутствует, явного пакета шрифтов нет. Setup проверяет запуск soffice, проверки кириллицы и font embedding нет. Это устанавливает пробел воспроизводимости, но не доказывает отсутствие подходящих шрифтов в установленном Debian. [system-requirements.apt:1](system-requirements.apt:1), [setup-wsl.sh:65](scripts/setup-wsl.sh:65).

Репозиторного Dockerfile не обнаружено. `docker-ci-parity.sh` рассчитан на `python:3.12` и устанавливает Python-зависимости. `ci.yml` тоже не устанавливает LibreOffice, а основной набор исключает `system_deps`. Поэтому обязательную реальную проверку PDF нужно назначить конкретному окружению. Обычный CI может проверять DOCX и сценарии ошибок через подмену конвертера. [docker-ci-parity.sh:2](scripts/docker-ci-parity.sh:2), [ci.yml:76](.github/workflows/ci.yml:76), [ci.yml:92](.github/workflows/ci.yml:92).

### 8. P2 · Высокая уверенность — сохранённые данные не являются готовым replay записей озвучки

Пересчёт указанного TXT подтвердил **1 224 абзаца, максимум 4 025 символов, 0 абзацев свыше 5 000**. В отчёте записаны 1 227 доставленных записей и три склейки. Это согласованные исторические величины. [report.json:317](/D:/Temp/docxai-research/070-fr009/runs/archive/20261110T074147Z_40074_money_full_standard_translated_ru/audiobook_money_full_standard_translated_report.json:317), [Money_Sustainability_full_standard_translated.tts.txt:921](/D:/Temp/docxai-research/070-fr009/runs/archive/20261110T074147Z_40074_money_full_standard_translated_ru/Money_Sustainability_full_standard_translated.tts.txt:921).

Однако отчёт указывает SHA `24391ce`. После него изменились восстановление заголовков и исключения. В сохранённом `runtime.state` нет полного набора `NarrationParagraphRecord` с ролями и уровнями. Раннер сохраняет итоговые тексты и реестры, а прототип сопоставляет TXT с текущими ожидаемыми ID по позиции и требует равного количества. На полной книге это предположение уже нарушают три детерминированные склейки. [report.json:34](/D:/Temp/docxai-research/070-fr009/runs/archive/20261110T074147Z_40074_money_full_standard_translated_ru/audiobook_money_full_standard_translated_report.json:34), [070/spec.md:335](specs/070-audiobook-technical-pass/spec.md:335), [run_lietaer_validation.py:6357](tests/artifacts/real_document_pipeline/run_lietaer_validation.py:6357), [build_probe_docx.py:41](/D:/Temp/docxai-research/elevenlabs-studio/build_probe_docx.py:41).

Для SC-001 нужно определить воспроизводимый offline fixture с ID, ролями, уровнями и группами склеек либо получить записи нового прогона. Архив остаётся допустимым материалом для проверки рендерера при явно зафиксированной версии входа.

**23 серии заголовков я независимо не подтвердил.** `heading_levels.py` вычисляет их через подготовку в WSL, сохранённого вывода рядом нет. Число нельзя повышать до нового измерения этого ревью. Кроме того, скрипт читает `p.heading_level`, тогда как FR-002 задаёт источник уровня через Markdown-префикс. Их соответствие требует проверки. [heading_levels.py:31](/D:/Temp/docxai-research/elevenlabs-studio/heading_levels.py:31), [spec.md:98](specs/072-narration-docx-pdf/spec.md:98).

### 9. P2 · Высокая уверенность — лимиты и проверка Studio имеют неполные критерии

FR-006 не определяет подсчёт абзацев до первого `Heading 1` и в документе без заголовков. У документа без заголовков счётчик глав может честно равняться нулю, но все его абзацы должны участвовать в проверке ограничения 400. Длину нужно считать после слияния заголовков. Требуются проверки границ 500/501, 400/401 и 5 000/5 001. [spec.md:86](specs/072-narration-docx-pdf/spec.md:86), [spec.md:112](specs/072-narration-docx-pdf/spec.md:112).

FR-009 проверяет импорт одной главы RM. Единственная глава в Studio могла бы получиться и без распознавания заголовков. Для подтверждения механизма нужен файл **продуктовой сборки минимум с двумя `Heading 1`**, проверка их границ, названий и отсутствия пропущенного текста перед первым заголовком. Новый платный LLM-прогон для такой проверки технически не обязателен. [spec.md:121](specs/072-narration-docx-pdf/spec.md:121), [spec.md:166](specs/072-narration-docx-pdf/spec.md:166).

## Проверка раздела «Что есть сейчас»

| Утверждение | Результат проверки |
|---|---|
| Writer сохраняет MD, DOCX, optional TXT и служебные файлы | Подтверждено. Уточнение об атомарности приведено в находке 1. [artifacts.py:363](src/docxaicorrector/runtime/artifacts.py:363) |
| Retention группирует по суффиксам | Подтверждено. Для новых файлов нужны оба точных суффикса `.result.tts.docx` и `.result.tts.pdf`. [artifact_retention.py:90](src/docxaicorrector/runtime/artifact_retention.py:90) |
| TXT собирается из записей, body+body соединяется пробелом | Подтверждено. `NarrationAssembly` сейчас возвращает текст и диагностику, структурированные группы остаются локальными. [narration_postprocess.py:138](src/docxaicorrector/pipeline/narration_postprocess.py:138) |
| В записи нет уровня заголовка | Подтверждено. [audiobook_pass.py:116](src/docxaicorrector/pipeline/audiobook_pass.py:116) |
| Проверочный DOCX содержит исключённые элементы и исходную структуру | Подтверждено кодом rebuild, восстановления свойств и вставки изображений. Предсказание конкретного поведения Studio остаётся предположением. [audiobook_pass.py:375](src/docxaicorrector/pipeline/audiobook_pass.py:375), [late_phases.py:455](src/docxaicorrector/pipeline/late_phases.py:455) |
| На экране три кнопки, событие содержит пути | Подтверждено. Указанный диапазон UI заканчивается раньше кнопки DOCX, она находится на строке 1229. [_ui.py:1195](src/docxaicorrector/ui/_ui.py:1195), [late_phases.py:1544](src/docxaicorrector/pipeline/late_phases.py:1544) |
| Pandoc строит DOCX, soffice используется при импорте | Подтверждено. Помимо двух конвертеров, поиск soffice повторён в `legacy_doc_conversion_available`. [_generation.py:3798](src/docxaicorrector/generation/_generation.py:3798), [processing_runtime.py:1282](src/docxaicorrector/processing/processing_runtime.py:1282) |
| Проба соответствует предполагаемому чистому DOCX | Частично. Отличия структуры и добавленный текст описаны в находке 4. [build_probe_docx.py:59](/D:/Temp/docxai-research/elevenlabs-studio/build_probe_docx.py:59) |

Документальные ссылки ElevenLabs корректны. Лимиты действительно указаны в сохранённой документации. Поддержка DOCX записана в changelog от 2 ноября. Инструкция про `Heading 1` относится к EPUB, что спека честно отмечает в Assumptions. [studio.md:703](/D:/Temp/docxai-research/elevenlabs-studio/raw/studio.md:703), [studio.md:981](/D:/Temp/docxai-research/elevenlabs-studio/raw/studio.md:981), [changelog.md:105](/D:/Temp/docxai-research/elevenlabs-studio/raw/changelog.md:105).

## Какой путь сборки реалистичен

**Выбрал бы python-docx с прямой записью текста.** Существующий Pandoc-путь включает preprocessing и читает `markdown+raw_html+superscript+subscript`, поэтому передача туда озвучиваемой строки нарушит FR-004 на специальных символах. `_build_reference_docx` пригоден как источник существующих правил оформления, но его numbering и прочее оформление проверочного документа новому минимальному экспорту целиком не требуются. [_generation.py:3820](src/docxaicorrector/generation/_generation.py:3820), [_generation.py:3945](src/docxaicorrector/generation/_generation.py:3945).

Единый путь сборки достижим.

- Уровень определяется один раз из `AudiobookParagraphInput.role` и `source_text` до потери исходного префикса. Затем он передаётся в запись и используется проверочным DOCX.
- `assemble_narration_records` отдаёт структурированные группы вместе с существующим TXT. DOCX потребляет эти группы с сохранением ID. Повторного определения body-склеек не требуется.
- `needs_review`, `source_restored` и `source_fallback` сохраняют свой окончательный очищенный текст. Новый экспорт не должен подставлять сырой исходник повторно или исключать эти записи. Такое поведение уже реализовано финализатором. [audiobook_pass.py:161](src/docxaicorrector/pipeline/audiobook_pass.py:161), [audiobook_pass.py:253](src/docxaicorrector/pipeline/audiobook_pass.py:253), [narration_postprocess.py:155](src/docxaicorrector/pipeline/narration_postprocess.py:155).

Для раннера нужно охватить сохранение файлов в run directory, `output_artifacts`, summary и latest aliases. Счётчики уже извлекаются из `ui_audiobook_artifact_saved`, поэтому второй вычислительный канал не требуется. [run_lietaer_validation.py:1591](tests/artifacts/real_document_pipeline/run_lietaer_validation.py:1591), [run_lietaer_validation.py:5052](tests/artifacts/real_document_pipeline/run_lietaer_validation.py:5052), [run_lietaer_validation.py:6384](tests/artifacts/real_document_pipeline/run_lietaer_validation.py:6384).

Имена скачивания следует явно закрепить как `<source-stem>.tts.docx/.tts.pdf/.tts.txt`. Дисковые имена дополнительно содержат timestamp/run ID и `.result`. UI-композиция из двух строк реализуема штатными `st.columns` и `width="stretch"`. Нужны browser-проверка, правильные MIME и доступность кнопок только для полученных форматов. [_ui.py:84](src/docxaicorrector/ui/_ui.py:84), [artifacts.py:163](src/docxaicorrector/runtime/artifacts.py:163), [AGENTS.md:498](AGENTS.md:498).

## Приёмка, границы и уровень работы

Без платного прогона проверяются сборка DOCX, точность символов, fallback-записи, уровни и слияния, лимиты, транспорт до UI, старые bundle, retention, отказы записи и конвертации. Реальный PDF требует WSL с LibreOffice и шрифтами. Распознавание глав Studio требует загрузки владельцем.

SC-001 следует проверять точной ожидаемой последовательностью преобразований с ID объединённых заголовков. Одного числа слияний недостаточно для объяснения изменения текста. Для SC-001/002/003 нужны отрицательные примеры с потерянным абзацем, лишним дублем и body, начинающимся с `#`. [spec.md:126](specs/072-narration-docx-pdf/spec.md:126), [constitution.md:325](.specify/memory/constitution.md:325).

Non-goals в основном соответствуют задаче. Слово «скачивание» стоит уточнить до скачивания **аудио**, поскольку скачивание DOCX/PDF входит в FR-008. Anti-regression стоит дополнить сохранением fallback-записей, очисткой новых session-полей, совместимостью старых bundle, изоляцией параллельных экспортов и сохранением существующих счётчиков. При обновлении контрактов нужно исправить устаревшее перечисление `mode/tag_count/excluded_blocks` в AGENTS.md — logging-документ уже описывает их удаление спекой 070. [spec.md:149](specs/072-narration-docx-pdf/spec.md:149), [AGENTS.md:466](AGENTS.md:466), [LOGGING_AND_ARTIFACT_RETENTION.md:416](docs/LOGGING_AND_ARTIFACT_RETENTION.md:416).

**Полный цикл оправдан** новым контрактом артефактов и данных между сборщиком, runtime, UI и раннером. Фактический подсчёт дал 72 каталога спецификаций и 9 `plan.md`. Наличие обязательных разделов у 072 подтверждено. Отметки checklist об однозначности требований и готовности следует пересмотреть после устранения перечисленных противоречий. [constitution.md:115](.specify/memory/constitution.md:115), [requirements.md:18](specs/072-narration-docx-pdf/checklists/requirements.md:18), [requirements.md:28](specs/072-narration-docx-pdf/checklists/requirements.md:28).

СТРОИТЬ ПОСЛЕ ПРАВОК
