# Tasks: составная иллюстрация PDF приходит одной картинкой

**Spec**: [spec.md](spec.md) | **Plan**: [plan.md](plan.md) | **Контракты**: [contracts/](contracts/) |
**Данные**: [data-model.md](data-model.md), [research.md](research.md) | **Проверка**: [quickstart.md](quickstart.md)

Tier: полный цикл (Конституция III). Фаза 2 (реализация) — отдельный бриф; задачи идут ПО ПОРЯДКУ одним исполнителем,
каждая заканчивается зелёной проверкой, названной в ней. Внутри задачи порядок: падающий тест → код → тест зелёный.

## Формат и общие правила

- `- [ ] T### [P?] [US?] [метки файлов] Описание — **Proof**: чем доказано`.
- Метки файлов (брифом требуется отмечать): **[RT]** — `src/docxaicorrector/processing/processing_runtime.py`;
  **[IMG]** — `src/docxaicorrector/pdf_import/images.py`; **[REQ]** — `requirements.txt` / `pyproject.toml`;
  **[DOC]** — документы. Задача правит ТОЛЬКО названные в ней файлы (Конституция VI); нужда в другом — вопрос
  оркестратору.
- Проверка — одна команда на selector, selector до опций:
  `wsl.exe -d Debian --cd "D:\Temp\claude\wt-082-impl" -- bash scripts/test.sh <selector> -q` (worktree фазы 2 вне
  репозитория, `.venv` — симлинк). Голый `python`, `.venv-win`, `py -m pytest` запрещены.
- **Конституция VII**: в коде и тестах — вымышленный текст («Label alpha», «An invented body sentence…»), ни строки,
  ни числа из книг корпуса; исключение — тест корпуса T024, который читает PDF из `tests/sources/book/` и сверяет
  счётчики. Числа правила — только из таблицы «Происхождение чисел» спеки.
- **Мутация**: у каждого стража — тест, который падает, когда условие снято; результат мутации (какой тест упал)
  записывается в Changelog спеки в T037.
- LF; `git diff --check` перед коммитом; тема коммита `spec 082: <что сделано>`; коммит — с переменными личности
  (AGENT_RULES); ни push, ни merge.

## Волны и зависимости

```text
Setup T001–T003 → Foundational T004–T008 → US1 T009–T026 → US2 T027–T031 → Polish T032–T040
```

US2 зависит от US1 целиком и отрезается без последствий для US1 (вопрос Q-1 спеки).

---

## Phase 1: Setup

- [ ] T001 [REQ] Добавить `pypdfium2==5.15.2` в `requirements.txt` и в `[project.optional-dependencies].pdf-import`
  `pyproject.toml`; в `scripts/setup-wsl.sh` (`verify_runtime`, `:65-72`) кортеж импортов += `"pdfminer"`,
  `"pypdfium2"`. — **Proof**: `tests/test_script_contract_static.py` зелёный; `python -I -c "import pypdfium2"` под WSL.
- [ ] T002 Помощник синтетического PDF `tests/pdf_synthetic.py` (не тестовый файл; инвентарь читает только `test_*.py`):
  порт `D:\Temp\claude\work-082\synth_pdf.py` в функцию `build_pdf(page, *, objects)` — размеры `MediaBox`, `CropBox`,
  `/Rotate`; объекты: Flate-битмап в `DeviceGray` (непередаваемый), JPEG в `DeviceGray` (передаваемый; Pillow в
  тесте), JPEG в `Separation` (US2), обводимый путь с толщиной, залитый прямоугольник, строка Helvetica заданного
  кегля в заданной точке. Вымышленный текст. — **Proof**: смоук-тест в `tests/test_pdf_figure_render.py`:
  `extract_pdf_text_spans_with_pdfminer` видит строки с заданными кеглями, `pdfminer` — `LTImage`/`LTLine`, pypdfium2
  рисует страницу нужного размера.
- [ ] T003 [RT] Характеристика ДО правки (зелёная на базе): сквозной тест `_convert_pdf_text_layer_to_docx` (seam
  `in-process`) на синтетике БЕЗ семени — передаваемый JPEG между двумя абзацами тела — снимок: тексты абзацев, порядок,
  байты картинки. Тест в `tests/test_processing_runtime.py`. — **Proof**: зелёный на базе; не правится до конца работы
  (Anti-regression 1, 5).

## Phase 2: Foundational

- [ ] T004 `pdf_import/logical_import.py`: `BodyTypography`, `measure_body_typography(spans)` (data-model §2) поверх
  `_detect_repeated_page_furniture_keys` + `_build_heading_layout_profile`. — **Proof**: тест в
  `tests/test_pdf_figure_regions.py`: синтетические спаны (предложения 11 pt, сноски 8 pt) → кегль 11,0 и ширина
  колонки; пустой список → `None`.
- [ ] T005 [IMG] `pdf_import/images.py`: `PdfPageGraphic`, `PdfPageGraphics`, `PdfImageExtraction`,
  `PdfImageObject.description` (data-model §1, §4); `extract_pdf_images_and_graphics(pdf_path, *, seed_kinds)` — тот
  же обход, что сегодня, плюс опись путей и признаков картинок; опись — только у страниц с семенем; итоговое событие
  НЕ эмитит. — **Proof**: тесты в `tests/test_pdf_figure_render.py` на синтетике: у битмапа `emittable=False`, у JPEG
  `True`, у JPEG в `Separation` `ink_space=True`; у обводимого пути `stroke_half_width = linewidth/2`; страница без
  семени в `seed_pages` не попадает; `images` на PDF из T003 — те же объекты, что выдавала старая функция.
- [ ] T006 [IMG] Классы данных data-model §3 (`FigureRegion`, `DeclinedFigureRegion`, `FigureRegionPlan`, константы
  видов) — в новом `src/docxaicorrector/pdf_import/figure_regions.py` БЕЗ логики правила; и
  `images.py::log_pdf_image_extraction_outcome(extraction, *, plan, rendered, failed, filename)` по
  `contracts/events.md` (при пустом плане — прежние ключи и значения + нулевые новые); она же эмитит
  `pdf_figure_region_declined` на каждую отклонённую область плана (правило — чистое и не логирует). — **Proof**:
  тест: без областей `discovered/emitted/skipped` как у прежнего события; с поглощёнными — `skipped` их не считает,
  уровень INFO; отклонённая область → одно событие отказа с причиной.
- [ ] T007 [IMG] [RT] Удалить `extract_pdf_images_with_pdfminer` и его экспорт (`pdf_import/__init__.py:14-27`);
  `_run_pdf_parse_stages` (`processing_runtime.py:529`, `:580-592`) вызывает новую точку входа и
  `log_pdf_image_extraction_outcome` с пустым планом. Поведение — прежнее. — **Proof**: T003 зелёный.
- [ ] T008 [RT] Перевести подмены старой функции в `tests/test_processing_runtime.py` (`:2124`, `:2188`, `:2941`,
  `:2999`; тесты событий `:3348-3402` — на `extract_pdf_images_and_graphics` + `log_pdf_image_extraction_outcome`),
  проверяемые утверждения не менять. — **Proof**: `tests/test_processing_runtime.py` зелёный целиком.

## Phase 3: User Story 1 — схема приходит одной картинкой (P1)

**Goal**: FR-001…FR-014 с семенем «непередаваемая картинка». **Independent Test**: синтетика T019 и корпус T024.

### Правило (чистое, без PDF)

- [ ] T009 [US1] Падающие тесты правила в `tests/test_pdf_figure_regions.py` на рамках (без PDF): схема как на
  стр. 151 в миниатюре (непередаваемый битмап + пути + 4 подписи 8 pt внутри + строки тела 11 pt выше и ниже) → одна
  область, подписи убраны, тело — нет; страница без семени → пустой план; `typography=None` → пустой план; две схемы,
  далёкие друг от друга → две области; близкие (зазор ≤ медиане высоты строки) → одна; схема во всю страницу без
  текста тела → область во всю страницу; допуск близости на странице без строк — медиана высоты строки книги. —
  **Proof**: падают (модуля нет).
- [ ] T010 [US1] Падающие тесты стражей и роста — по одному условию на тест, в докстринге — условие, снятие которого
  его роняет (SC-005): **G1** строка тела внутри → отказ `body_size_text`; **без буквы** — «%» 24 pt внутри → область
  принимается; **G2** полная строка мелкого кегля (≥ 0,72 колонки) внутри → отказ `full_measure_line`; **рост «мельче
  тела»** — подпись 8 pt за краем втягивается, строка 11 pt за краем — нет (и при центре внутри → отказ G1);
  **защита подписи** — строка формы подписи за краем не втягивается, внутри — не убирается; **«целиком внутри»** —
  строка, пересекающая край кеглем тела с центром снаружи, не убирается. — **Proof**: падают.
- [ ] T011 [US1] Инварианты (тот же файл): убранные строки ⊆ области; области одной страницы не пересекаются; сумма
  знаков убранных строк = `suppressed_char_count`; ни одна строка формы подписи не убрана; `raster_density_dpi` —
  взвешенная медиана (обломок 3×3 px в 1 pt² не двигает её). — **Proof**: падают.
- [ ] T012 [US1] `detect_figure_regions` в `src/docxaicorrector/pdf_import/figure_regions.py` по data-model §3 (порт
  `work-082/rule.py::detect_regions`, режим `grow=small`, `guard=letter`, `full_guard`, `protect_caption`): числа — только
  `_font_sizes_match`, `_FULL_LINE_FILL_RATIO`, `_looks_like_caption` из `logical_import.py` и величины страницы. —
  **Proof**: T009–T011 зелёные; затем мутация — снять по очереди каждое условие T010 и убедиться, что падает свой тест
  (записать для T037).

### Отрисовка

- [ ] T013 [US1] Падающие тесты чистых помощников в `tests/test_pdf_figure_render.py`: `region_resolution_dpi` (без
  потолка — плотность как есть; потолок 12000 px по стороне и 50 Мп; константы читаются из `image/analysis.py`, не
  копируются); `region_crop` — сдвиг `MediaBox` с ненулевым началом, `CropBox` внутри `MediaBox` (сдвиг по x и y),
  рамка частично вне `CropBox` (обрезается), целиком вне (`None`), поворот 0/90/180/270, раздвижка `render_pad_pt`. —
  **Proof**: падают.
- [ ] T014 [US1] Падающие тесты отрисовки на синтетике: залитый чёрный квадрат в известной рамке на странице с
  `CropBox ≠ MediaBox` — на отрисовке области квадрат в ожидаемых пикселях (±1); то же с `/Rotate 90`; PNG несёт
  `pHYs` = dpi; серая страница → PNG `L`, цветная → `RGB`; две нити рисуют одновременно без сбоя (замок); документ
  не открывается при пустом плане (подмена `pypdfium2.PdfDocument` считает вызовы). — **Proof**: падают.
- [ ] T015 [US1] `src/docxaicorrector/pdf_import/figure_render.py` по data-model §5 и plan «FR-007…FR-009, FR-013»;
  события `pdf_figure_region_rendered` / `pdf_figure_region_render_failed` (contracts/events.md). — **Proof**:
  T013–T014 зелёные; мутация: убрать пересчёт `CropBox` → тест квадрата падает; убрать `pHYs` → тест плотности падает.

### Склейка и DOCX

- [ ] T016 [US1] [RT] Падающий сквозной тест в `tests/test_processing_runtime.py`: синтетика (битмап + путь + две
  подписи 8 pt внутри; тело 11 pt выше и ниже; подпись формы «Figure 9.9 …» ниже) через `_convert_pdf_text_layer_to_docx`
  → абзацы: тело, тело, подпись; ровно одна картинка между ними; ни одного абзаца подписей схемы. — **Proof**: падает.
- [ ] T017 [US1] [RT] Падающий тест размера (SC-006): ширина и высота картинки в DOCX (EMU) = рамка × 12700 ± один
  пиксель отрисовки; `wp:docPr/@descr` = «Label alpha Label beta» (порядок `top`, `x0`). — **Proof**: падает.
- [ ] T018 [US1] [RT] Падающий тест событий: `pdf_figure_region_rendered` с `lines_suppressed=2`,
  `chars_suppressed`, `images_absorbed`; итог `pdf_image_extraction_summary` INFO с `skipped=0`,
  `figure_regions_rendered=1`; `pdf_text_layer_import_succeeded` с двумя новыми ключами. — **Proof**: падает.
- [ ] T019 [US1] [RT] `_run_pdf_parse_stages` (`processing_runtime.py:580-601`): типографика → план → отрисовка →
  фильтр спанов и картинок ТОЛЬКО по отрисованным областям → картинки областей → сортировка → лимит картинок
  (`:592`) → итоговое событие; `_PdfParseStagesResult` (`:494-508`) += `figure_regions_rendered`,
  `figure_region_lines_suppressed` (умолчание 0); ключи в `pdf_text_layer_import_succeeded` (`:919-933`). —
  **Proof**: T016, T018 зелёные; T003 зелёный без правки.
- [ ] T020 [US1] [RT] `_append_image_bytes_to_docx(document, image_bytes, description=None)` и
  `_append_pdf_image_to_docx` (`:1057-1109`): описание → `shape._inline.docPr.set("descr", …)` (проверено на python-docx
  1.2.0 2026-11-13). — **Proof**: T017 зелёный.
- [ ] T021 [US1] [RT] Инвариант FR-011: подмена отрисовщика исключением → спаны и картинки страницы как без правила,
  событие ERROR `pdf_figure_region_render_failed`, итог `figure_regions_failed=1`. — **Proof**: тест падает до правки
  склейки (если склейка удаляет до отрисовки) и зелёный после; мутация «удалять по плану, а не по отрисованным» его
  роняет.
- [ ] T022 [US1] [RT] Отказ сквозь мост: синтетика со строкой тела внутри рамки схемы → страница как без правила
  (T003-подобный снимок), событие `pdf_figure_region_declined` с `reason=body_size_text`. — **Proof**: тест.
- [ ] T023 [US1] [RT] Ветка OCR (`:565-569`): подмена `_run_pdf_ocr_to_text_layer_pdf` копией входа и
  `build_text_layer_quality_report` «не promising, затем promising» → правило работает на спанах OCR-пути и графике
  входа; результат тот же, что без OCR. — **Proof**: тест.

### Корпус

- [ ] T024 [US1] `tests/test_pdf_figure_regions_corpus.py` (`pytestmark = pytest.mark.integration_local`): Rethinking
  PDF из `tests/sources/book/` — опись + спаны + план: одна область, стр. 151, рамка `[42.2, 68.2, 353.8, 499.5]` ± 0,1,
  283 поглощённых картинки, 2365 путей, 54 строки, 528 знаков; отрисовка — 150,2 ± 0,5 dpi, 649×899 ± 1 px. Счётчики —
  в тесте литералами с датой и ссылкой на спеку (это тест корпуса, не правило). — **Proof**: зелёный; ≈ 11 с.
- [ ] T025 [US1] `scripts/measure-composite-figure-regions.py`: четыре книги корпуса, для каждой — сборка абзацев и
  список картинок с правилом и без (`--seed-kinds`), разница последовательностей (как `work-082/sim.py`), таблица
  research R17; `--save-docx <каталог>` — промежуточный DOCX моста через `_convert_pdf_text_layer_to_docx`; `python -I`,
  `if __name__ == "__main__"`, `src` первым в `sys.path`. Строка в `scripts/README.md`. — **Proof**: прогон под WSL
  даёт числа R17 (US1); расхождение — стоп, вопрос оркестратору.
- [ ] T026 [US1] Глазами: DOCX из `--save-docx` для Rethinking — Figure 7.1 одной картинкой, Alt Text — подписи;
  записать в Changelog спеки. — **Proof**: запись.

## Phase 4: User Story 2 — фото в пространстве краски не негативы (P2, отрезаемо)

**Goal**: семя «картинка в `Separation`/`DeviceN`». **Independent Test**: синтетика T027, корпус T030.

- [ ] T027 [US2] Падающие тесты: синтетика с JPEG в `Separation` (Pillow: серый градиент; словарь `Separation` с
  функцией оттенка) — при `seed_kinds ⊇ {ink_space}` картинка заменена отрисовкой рамки; средняя яркость картинки
  совпадает со страницей (не с инверсией); `description` пуст; при `seed_kinds = {non_emittable}` — картинка прежняя.
  Тесты в `tests/test_pdf_figure_render.py` и `tests/test_processing_runtime.py`. — **Proof**: падают.
- [ ] T028 [US2] [IMG] Признак `ink_space` уже в описи (T005); `figure_regions.py` — вид семени `ink_space`
  (`non_emittable` побеждает, если оба). — **Proof**: T027 (правило) зелёный.
- [ ] T029 [US2] [RT] Умолчание `seed_kinds` в `_run_pdf_parse_stages` — оба вида. — **Proof**: T027 (мост) зелёный;
  T003 зелёный.
- [ ] T030 [US2] Тест корпуса T024 += 33 области на Rethinking (31 — рамка фото, стр. 276 — рамка + 2 пути), ни одной
  убранной строки вне стр. 151; замерный скрипт — числа R17 «US1+US2». — **Proof**: зелёный тест; прогон скрипта.
- [ ] T031 [US2] Глазами: 3 фото Rethinking из `--save-docx` (стр. 26, 96, 176) — не негативы. — **Proof**: запись
  в Changelog.

## Phase 5: Polish & Cross-Cutting

- [ ] T032 [DOC] `docs/LOGGING_AND_ARTIFACT_RETENTION.md`: `pdf_image_extraction_*` — из §3.8 в описанные с новыми
  ключами; новый подраздел «Спека 082: области иллюстраций PDF» (три события); запись в §7. `scripts/_list_log_events.py`
  `TARGETS` += `src/docxaicorrector/pdf_import/images.py`, `src/docxaicorrector/pdf_import/figure_render.py`. —
  **Proof**: `tests/test_documentation_links.py`, `tests/test_script_contract_static.py` зелёные.
- [ ] T033 [DOC] `docs/WORKFLOW_AND_IMAGE_MODES.md` (Runtime Workflow, `:19-21`; Image Modes): составная иллюстрация PDF
  приходит одной картинкой (`pypdfium2`, без системного пакета); режимы изображений получают её как любую картинку. —
  **Proof**: `tests/test_documentation_links.py`.
- [ ] T034 [DOC] `AGENTS.md`, «Прочее по runtime» (абзац о PDF, `:213-217`): области иллюстраций рисует `pypdfium2` из
  `requirements.txt`; системный пакет не нужен. — **Proof**: `tests/test_agent_contract_consistency.py`.
- [ ] T035 [DOC] `docs/testing/TEST_TIER_INVENTORY.md`: `tests/test_pdf_figure_regions.py`,
  `tests/test_pdf_figure_render.py` — Unit-Contract; `tests/test_pdf_figure_regions_corpus.py` — Integration-Local. —
  **Proof**: `tests/test_script_contract_static.py`.
- [ ] T036 `tests/test_typecheck.py` (timeout ≥ 180000 мс) — без новых ошибок сверх базы. — **Proof**: зелёный.
- [ ] T037 [DOC] `spec.md` Changelog: результаты мутаций T012/T015/T021, числа T025/T030, проверка глазами T026/T031,
  `file:line` итогового кода; статус — по факту (оркестратор решает формулировку и строку `docs/WHERE_WE_ARE.md`). —
  **Proof**: `tests/test_spec_status_consistency.py` (в боковом worktree тесты истории пропускаются — проверка в
  главном дереве за оркестратором).
- [ ] T038 Прогоны затронутых файлов отдельными командами: `tests/test_pdf_figure_regions.py`,
  `tests/test_pdf_figure_render.py`, `tests/test_pdf_figure_regions_corpus.py`, `tests/test_processing_runtime.py`,
  `tests/test_pdf_text_layer_logical_import.py`, `tests/test_pdf_text_layer_quality.py`,
  `tests/test_script_contract_static.py`, `tests/test_documentation_links.py`, `tests/test_agent_contract_consistency.py`. —
  **Proof**: зелёные, счёт `passed` дословно в отчёте.
- [ ] T039 Оркестратор: полный прогон `scripts/test.sh tests/ -q` в главном дереве после слияния; `git status
  --porcelain` пуст; первый CI-прогон ветки подтверждает установку колеса.
- [ ] T040 Оркестратор: приёмочное ревью Codex по затронутым поверхностям (`images.py`, `figure_regions.py`,
  `figure_render.py`, `logical_import.py` целиком, `processing_runtime.py` целиком, их тесты, вызывающие); отчёт
  `docs/reviews/CODEX_REVIEW_082_<дата>.md`.

## Сводка

- Задач: 40 (Setup 3, Foundational 5, US1 18, US2 5, Polish 9).
- Трогают **[RT]** `processing_runtime.py`: T003 (тест), T007, T008 (тест), T016–T023, T029.
- Трогают **[IMG]** `images.py`: T005, T006, T007, T028.
- Трогают **[REQ]**: T001. **[DOC]**: T032–T035, T037.
- MVP — US1 (T001–T026). US2 — T027–T031, отрезаемы.
