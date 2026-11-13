# Implementation Plan: составная иллюстрация PDF приходит одной картинкой

**Branch**: `082-composite-figure` (от `main` @ `9b5db10`) | **Date**: 2026-11-13 | **Spec**: [spec.md](spec.md)

**Input**: `specs/082-composite-figure-region/spec.md`; решения — [research.md](research.md) (R1–R17); сущности —
[data-model.md](data-model.md); контракты — [contracts/events.md](contracts/events.md),
[contracts/import-output.md](contracts/import-output.md); проверка — [quickstart.md](quickstart.md); задачи —
[tasks.md](tasks.md).

**База**: `main` @ `9b5db10`. Все `file:line` сверены на нём 2026-11-13. Если ветка фазы 2 уйдёт вперёд — сверить
заново (Конституция VIII); расхождение — вопрос оркестратору.

## Summary

Импорт PDF по текстовому слою находит на странице «составную иллюстрацию» — рисунок из картинок и путей, в котором
есть картинка, которую извлекатель не отдаёт (US1) или которая хранится в пространстве краски (US2), — растит её рамку
до соседних рисунков и мелких подписей, отказывается, если внутри текст тела или полная строка, и заменяет всё это
одной PNG-отрисовкой рамки (`pypdfium2`), с подписями внутри как пикселями и их текстом в Alt Text. Всё — до DOCX, в
дочернем процессе разбора, под его сроком; ядро конвейера видит обычную картинку. На корпусе меняется одна страница
(Rethinking 151) и, с US2, 32 фотографии той же книги; три другие книги — побайтно те же.

## Technical Context

**Language/Version**: Python 3.13.5 (WSL `.venv`), CI — 3.12 (`.github/workflows/ci.yml`).

**Primary Dependencies**: `pdfminer.six` 20260107 (есть); **новая** `pypdfium2==5.15.2` (колесо `py3-none-manylinux_2_17_x86_64`,
BSD-3/Apache-2.0); Pillow 12.3.0 (есть; PNG и `pHYs`); python-docx 1.2.0 (есть; `docPr/@descr`).

**Storage**: нет новых артефактов; картинка области живёт в промежуточном DOCX моста, события — в `app.log`.

**Testing**: pytest через `bash scripts/test.sh` под WSL; синтетический PDF, собранный байтами в тесте (research R16);
тест корпуса `integration_local` на Rethinking; замерный скрипт на четырёх книгах — при приёмке.

**Target Platform**: WSL Debian, x86_64; CI ubuntu-latest.

**Project Type**: одно Python-приложение `src/docxaicorrector/`.

**Performance Goals**: + ≤ 5 с на импорт Rethinking (замер 1,85 с на 33 области; детекция 0,1 с); обход путей — в уже
идущем обходе страниц, без третьего прохода `pdfminer` (он стоил бы 5–16 с на книгу).

**Constraints**: ни одной страницы без семени не трогать (по построению); текст не убирается без картинки; ни числа,
ни строки из книг корпуса в коде и тестах; нет системного пакета; нет пользовательской ветки «деградации».

**Scale/Scope**: 2 новых модуля (`figure_regions.py` ~250 строк, `figure_render.py` ~200), правки 3 модулей
(`images.py`, `logical_import.py` — одна функция, `processing_runtime.py`), 3 новых тестовых файла + правки
`tests/test_processing_runtime.py`, 1 замерный скрипт, 5 документов, 2 файла зависимостей, `setup-wsl.sh`.

`NEEDS CLARIFICATION` нет; три инженерных вопроса к оркестратору — в спеке («Открытые вопросы» Q-1…Q-3); они не
блокируют US1 (по умолчанию: US2 — включено отдельными задачами, рост — «мельче тела», сбой — страница как сегодня).

## Constitution Check

### До дизайна

- **I/II — PASS.** Замеры — `.venv` под WSL (`D:\Temp\claude\work-082\`, вне git); проверки фазы 2 — `scripts/test.sh`
  через `wsl.exe -d Debian`; замер корпуса — скрипт репозитория.
- **III — PASS, полный цикл**: два новых модуля, новая зависимость, новый вид картинки и поля событий; порядок изменения
  модулей важен (опись → правило → отрисовка → склейка).
- **IV — PASS.** Реальные документы — вход офлайн-замера, без модели; никаких «провалов прогона» спека не разбирает.
- **V — PASS.** События, поля, уровни — `contracts/events.md`; артефактов нет; документ логирования обновляется задачей.
- **VI — PASS.** Каждая задача называет свои файлы; `processing_runtime.py` трогают ровно T003, T007, T008, T016–T023, T029
  (сводка `tasks.md`).
- **VII — PASS с обязательствами.** Правило — геометрия, кегль, класс символа и роли импортёра; числа — величины
  документа или существующие константы кода (таблица «Происхождение чисел» спеки). Форма подписи — существующая
  константа импортёра `_CAPTION_PATTERN`, не новый список. Тесты — вымышленный текст. Правило, вычитающее текст
  (убранные строки), несёт контрдоказательство: строки тела и полные строки внутри — отказ (G1/G2), доказано мутацией
  на синтетике и замером на корпусе (испытание 2: без G2 19 страниц, без G1 37 страниц ушли бы в картинку).
- **VIII — PASS.** Ссылки сверены 2026-11-13 на `9b5db10`; две посылки обследования 2026-11-12 перепроверены и
  исправлены (research R2, R3, R6); ожидаемые числа — из симуляции производственными функциями этого дерева.

### После дизайна

PASS. Отклонения от брифа, обоснованные замером: разрешение — взвешенная медиана, не максимум (R7); второй вид
семени — пространство краски, не обтравка (R6). Complexity Tracking не нужен.

## Project Structure

### Документация (эта спека)

```text
specs/082-composite-figure-region/
├── spec.md
├── plan.md                  # этот файл
├── research.md              # R1–R17 с замерами
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── events.md            # три новых события, изменённый итог извлечения
│   └── import-output.md     # спаны, картинки, DOCX, зависимость
├── checklists/requirements.md
└── tasks.md
```

### Исходный код (затронуто / создано)

```text
src/docxaicorrector/pdf_import/
├── images.py              # ИЗМ.: опись графики в том же обходе; PdfImageObject.description;
│                          #       extract_pdf_images_and_graphics; итоговое событие после областей
├── figure_regions.py      # НОВ.: чистое правило (FR-001…FR-006)
├── figure_render.py       # НОВ.: pypdfium2, координаты, разрешение, PNG (FR-007…FR-009, FR-013)
├── logical_import.py      # ИЗМ.: только measure_body_typography (обёртка над профилем)
└── __init__.py            # ИЗМ.: экспорт новой точки входа вместо extract_pdf_images_with_pdfminer
src/docxaicorrector/processing/processing_runtime.py
                           # ИЗМ.: _run_pdf_parse_stages (склейка), _PdfParseStagesResult (+2 поля),
                           #       _append_pdf_image_to_docx/_append_image_bytes_to_docx (descr),
                           #       pdf_text_layer_import_succeeded (+2 ключа)
requirements.txt, pyproject.toml          # ИЗМ.: pypdfium2==5.15.2
scripts/setup-wsl.sh                       # ИЗМ.: verify_runtime импортирует pdfminer, pypdfium2
scripts/_list_log_events.py                # ИЗМ.: TARGETS += images.py, figure_render.py
scripts/measure-composite-figure-regions.py  # НОВ.: замер корпуса (+ --save-docx)
scripts/README.md                          # ИЗМ.: строка о скрипте
tests/test_pdf_figure_regions.py           # НОВ.: правило на рамках (unit_contract)
tests/test_pdf_figure_render.py            # НОВ.: синтетический PDF, координаты, PNG (unit_contract)
tests/test_pdf_figure_regions_corpus.py    # НОВ.: Rethinking стр. 151 (integration_local)
tests/test_processing_runtime.py           # ИЗМ.: подмены извлекателя; сквозной тест моста
docs/LOGGING_AND_ARTIFACT_RETENTION.md, docs/WORKFLOW_AND_IMAGE_MODES.md, AGENTS.md (Прочее по runtime),
docs/testing/TEST_TIER_INVENTORY.md        # ИЗМ.
```

## Дизайн по требованиям

### FR-001 — опись графики (`images.py`)

Обход `_iter_pdfminer_images` (`:129-143`) обобщается до обхода графики: картинки — как сейчас (байты, mime, рамка), плюс
для КАЖДОЙ картинки — `PdfPageGraphic` с `emittable`, `ink_space`, `source_px`, `discovery_index`; пути (`LTCurve`)
— рамка и `stroke_half_width` (`linewidth / 2`, если `stroke`). Опись страницы сохраняется, только если на ней есть
семя выбранных видов (data-model §1) — на корпусе 1 (или 33) страниц из 917. Публичная точка входа —
`extract_pdf_images_and_graphics(pdf_path, *, seed_kinds) -> PdfImageExtraction`; `extract_pdf_images_with_pdfminer`
удаляется вместе с экспортом (`__init__.py:14-27`) — вызывал его только `processing_runtime.py:529`, `:581`; тесты-подмены
переводятся (T007). Без совместимого псевдонима (решение владельца 2026-11-08 «без compat aliases»).

### FR-002…FR-006 — правило (`figure_regions.py`)

Порт `work-082/rule.py::detect_regions` в типизированный модуль: union-find по рамкам с отсечением по x (как в замере);
допуск — медиана высоты строк страницы; рост до неподвижности; стражи; результат — `FigureRegionPlan`. Входы: опись
(только страницы с семенем), ВСЕ спаны (индексы спанов — позиции в переданном списке), `BodyTypography`. Строки — спаны с
непустым `_normalize_text` (как в импортёре). Модуль не импортирует `pdfminer` и `pypdfium2`.

### FR-005 — типографика (`logical_import.py`)

`measure_body_typography(spans)` = `_detect_repeated_page_furniture_keys` + `_build_heading_layout_profile` на
нормализованных спанах — те же вызовы, что в начале `build_paragraph_units_from_text_spans` (`:149-160`); возвращает
`BodyTypography` или `None`. Стоимость — один дополнительный расчёт профиля на книгу (секунды нет: профиль считается
за один проход спанов) — замер в T005.

### FR-007…FR-009, FR-013 — отрисовка (`figure_render.py`)

`import pypdfium2` внутри функции; `threading.Lock` уровня модуля вокруг открытия документа и отрисовки. Для каждой
области: `region_resolution_dpi` (FR-008), `region_crop` (FR-009; рамка + `render_pad_pt`, пересечение с `CropBox`,
поворот 0/90/180/270), `page.render(scale=dpi/72, crop=..., draw_annots=False, may_draw_forms=False)`, PIL → если R=G=B
попиксельно — `L`; PNG с `dpi=(dpi, dpi)`. Документ открывается один раз на книгу и только при непустом плане.
Возврат — отрисованные и сбойные области раздельно.

### FR-006, FR-010, FR-011, FR-014 — склейка (`processing_runtime.py::_run_pdf_parse_stages`, `:580-601`)

После `extract_pdf_images_and_graphics`: `typography = measure_body_typography(spans)`; `plan = detect_figure_regions(...)`;
`rendered, failed = render_figure_regions(input_path, plan)`; из спанов убираются `suppressed_span_indices` ТОЛЬКО
отрисованных областей; из картинок — отдаваемые с `discovery_index` из их `absorbed_discovery_indices`; добавляются
картинки областей; сортировка `(page, top, x0)`; `_enforce_pdf_image_count_cap` — после; итоговое событие (contracts).
Исключение внутри шага областей целиком (не отрисовки одной области) не перехватывается: это дефект кода, и разбор
падает как сегодня падает любая ошибка стадии (`:662-663`). Ветка «OCR» (`:565-569`): спаны после OCR — из
`ocr_output_path`, картинки — из `input_path` (как сегодня); правило работает на этих спанах и графике `input_path`
(рамки страниц совпадают — `ocrmypdf` не меняет геометрию; **[вывод]**, тест — T024).

### FR-010 — DOCX (`processing_runtime.py:1057-1109`)

`_append_image_bytes_to_docx(document, image_bytes, description=None)`: `shape = run.add_picture(...)`; при описании —
`shape._inline.docPr.set("descr", description)`. `_append_pdf_image_to_docx` передаёт `getattr(image_object, "description", None)`.

### FR-012 — события

`images.py::log_pdf_image_extraction_outcome(extraction, *, plan, rendered, failed, filename)` эмитит итог (одна
функция владеет именами событий извлечения); `pdf_figure_region_*` — из `figure_render.py` (отрисовка/сбой) и
`figure_regions.py` не логирует (чистый) — отказы логирует склейка через ту же функцию `images.py`.

## Порядок реализации

Один исполнитель, задачи по порядку (`tasks.md`); параллельность не нужна — модули зависят цепочкой.

```text
Setup:        T001–T003   зависимость, кэш-независимая синтетика PDF-помощника
Foundational: T004–T008   типографика, опись графики, новая точка входа, перевод подмен
US1:          T009–T026   правило → отрисовка → склейка → DOCX → события → корпус
US2:          T027–T031   семя «пространство краски» (отрезаемо)
Polish:       T032–T040   документы, инвентарь тестов, замер корпуса, гарды, приёмка
```

## Риски

| Риск | Чем закрыт |
|---|---|
| Правило уводит в картинку полезный текст | G1/G2 + защита подписи; испытание 2 (каждая страница корпуса под картинкой) — 0 ложных; мутационные тесты; события с началом убранного текста; Alt Text |
| Сдвиг картинки из-за `CropBox` | чистая функция координат + тест на синтетике с `CropBox` и пиксельной проверкой |
| Картинка в DOCX не того размера | `pHYs`; тест EMU = рамка (SC-006) |
| Регрессия на книгах без иллюстраций | по построению (нет семени — нет обработки); SC-002 замером |
| PDFium в потоке тестов | замок модуля |
| Колесо не ставится в CI | `py3-none-manylinux_2_17_x86_64`; первый CI-прогон ветки — проверка |
| pyright-ратчет | новые модули типизированы; `test_typecheck.py` в задачах; `reportMissingImports` — warning (`pyrightconfig.json`) для job без `pdf-import` |
| Срок разбора | + 1,9 с на корпусе; область — в том же ребёнке |

## Сохраняемые контракты AGENTS.md

- WSL — источник истины; проверки через `scripts/test.sh` и транспорт `wsl.exe -d Debian`; debug-пути помечаются.
- Боковой worktree: `.venv` — симлинк; `git` — из Git Bash; тесты истории — в главном дереве.
- LF; `git diff --check` перед коммитом.
- Тема коммита называет спеку 082 только для работы по ней.
- Логирование — `log_event`, имена из контракта, текст ≤ 120 знаков.
- Перед «зелёным» — `git status --porcelain` пуст; полный прогон в главном дереве после слияния; приёмочное ревью Codex
  по затронутым поверхностям (все модули с hunk'ами целиком + вызывающие и вызываемые) — за оркестратором.

## Что не определено (сказано прямо)

- Верность отрисовки проверена на 15 страницах корпуса против Ghostscript и глазами; эталона нет.
- Поведение на PDF с поворотом и на сканах с текстовым слоем — только синтетика и испытание 2 (подложенная картинка),
  настоящих таких книг в корпусе нет.
- Вид схемы при битмапах ниже 100 dpi не мерился (в корпусе нет).
- Q-1…Q-3 спеки — решения оркестратора.
