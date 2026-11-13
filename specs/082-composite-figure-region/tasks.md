# Tasks: картинки PDF — такими, какими их видит читатель страницы

**Spec**: [spec.md](spec.md) | **Plan**: [plan.md](plan.md) | **Контракты**: [contracts/](contracts/) |
**Данные**: [data-model.md](data-model.md), [research.md](research.md) | **Проверка**: [quickstart.md](quickstart.md)

Tier: полный цикл (Конституция III). Раунд 2 (после ревью дизайна): задачи T001–T039 — **срез A** (сделано, история);
задачи среза B T040–T054 — по редакции 2026-11-13 (решение владельца D-6), выполняются после второго ревью дизайна (T040). Задачи идут по порядку одним исполнителем; внутри задачи: падающий
тест → код → зелёный тест.

## Формат и общие правила

- `- [ ] T### [метки] Описание — **Proof**: чем доказано`. Метки файлов: **[RT]** —
  `src/docxaicorrector/processing/processing_runtime.py` (только путь картинок); **[IMG]** —
  `src/docxaicorrector/pdf_import/images.py`; **[REQ]** — `requirements.txt` / `pyproject.toml`; **[DOC]** — документы.
  Задача правит только названные файлы; `pdf_import/logical_import.py` — только чтение.
- Проверка — одна команда на selector: `wsl.exe -d Debian --cd "D:\Temp\claude\wt-082" -- bash scripts/test.sh <selector> -q`.
- **Конституция VII**: тексты тестов вымышленные; ни строки, ни числа из книг корпуса, кроме теста корпуса T012.
- **Мутация**: у каждого условия триггера и каждого отказа — тест, падающий при снятии условия; результат — в Changelog
  спеки (T018).
- LF; `git diff --check`; тема коммита `spec 082: …`; ни push, ни merge.

## Phase 1: Setup

- [x] T001 [REQ] `pypdfium2==5.15.2` в `requirements.txt` и `[project.optional-dependencies].pdf-import` `pyproject.toml`;
  `scripts/setup-wsl.sh` `verify_runtime` импортирует `pdfminer`, `pypdfium2`. — **Proof**:
  `tests/test_script_contract_static.py`; `python -I -c "import pypdfium2"`.
- [x] T002 `tests/pdf_synthetic.py`: сборщик PDF байтами — страница (`MediaBox`, `CropBox`, `/Rotate`), JPEG в `DeviceGray`
  и в `Separation` (Pillow), Flate-битмап, обводимый путь, залитый прямоугольник, строка Helvetica заданного кегля. —
  **Proof**: смоук-тест в `tests/test_pdf_page_render.py` (pdfminer видит спаны и `LTImage`, pypdfium2 рисует).
- [x] T003 [RT] Характеристика ДО правки: мост `_convert_pdf_text_layer_to_docx` на синтетике без триггера (JPEG
  `DeviceGray` между абзацами) — тексты абзацев, порядок, sha1 картинки — в `tests/test_processing_runtime.py`. —
  **Proof**: зелёный на базе и после каждой следующей задачи без правки.

## Phase 2: Foundational

- [x] T004 [IMG] [RT] `images.py`: `PdfDiscoveredImage`, `PdfImageExtraction`, новые поля `PdfImageObject`,
  `extract_pdf_images_and_inventory`, `log_pdf_image_extraction_outcome` (прежние ключи + нулевые новые);
  `extract_pdf_images_with_pdfminer` и её экспорт удалены; `_run_pdf_parse_stages` вызывает новую точку входа (поведение
  прежнее); подмены в `tests/test_processing_runtime.py` переведены. — **Proof**: новые тесты описи (ключ, семейство,
  `skip_reason`, одинаковые `discovery_index` на разных страницах — разные ключи) и `tests/test_processing_runtime.py`
  целиком; T003.

## Phase 3: Срез A (US1)

- [x] T005 `pdf_import/page_render.py`: `layout_cropbox`, `frame_geometry` (чистые) — тесты в `tests/test_pdf_page_render.py`:
  округление наружу (пикселей ≥ `w_pt·scale`, `h_pt·scale`), сдвиг `CropBox`, частично вне `CropBox`, целиком вне → `None`,
  поворот 0/90/180/270, фактическая рамка в pt. — **Proof**: тесты; мутация «без округления наружу» роняет тест пикселей.
- [x] T006 `page_render.render_frames` (pypdfium2, замок, PNG `L`/`RGB`, `pHYs`) — тесты на синтетике: чёрный квадрат на
  странице с `CropBox ≠ MediaBox` и с `/Rotate 90` — в отрисовке рамки, найденной pdfminer, на ожидаемых пикселях; серая
  страница → `L`; цветная → `RGB`; пустой запрос не открывает документ. — **Proof**: тесты; мутация «без `CropBox`» роняет
  тест квадрата.
- [x] T007 `pdf_import/image_frames.py`: `colour_space_is_ink`, `plan_frame_replacements` — тесты в
  `tests/test_pdf_image_frames.py`: `Separation` и `DeviceN` — кандидаты; `DeviceGray`, `DeviceRGB`, `ICCBased`, `Indexed`,
  `None` — нет; строка поверх рамки → `text_over_frame`; строка, касающаяся рамки краем (нулевая площадь), — не отказ;
  другая картинка поверх → `image_over_frame`; масштаб = плотность источника. — **Proof**: тесты; мутации (снять проверку
  семейства / отказ по тексту / отказ по картинке) роняют каждая свой тест.
- [x] T008 `image_frames.apply_frame_replacements` и события (contracts/events.md) — тесты: замена несёт PNG, `display_*`,
  `original_*`, тот же `source_index`/рамку/ключ; пикселей не меньше источника; `exceeds_pixel_budget` (подмена
  потолка); сбой отрисовки → исходные байты + ERROR; события с ключами контракта. — **Proof**: тесты.
- [x] T009 [RT] `_run_pdf_parse_stages`: опись → план → замены → итоговое событие → лимит; исключение шага замен →
  исходные картинки + ERROR. Сквозной тест моста: JPEG `Separation` между абзацами → в DOCX картинка, средняя яркость
  которой как у страницы (не как у инверсии); спаны и абзацы те же; итог WARNING/INFO с новыми счётчиками. — **Proof**:
  тесты; T003 зелёный.
- [x] T010 [RT] `_append_image_bytes_to_docx(document, bytes, width_pt=None, height_pt=None)`; замена — с явным размером;
  сбой вставки замены → исходные байты прежним путём + ERROR `pdf_image_replacement_insert_failed`. Тесты: EMU = рамка ×
  12700 на дробной плотности (217,5 dpi) и на рамке, обрезанной `CropBox`; подмена `add_picture` исключением для PNG →
  исходный JPEG в DOCX + ERROR. — **Proof**: тесты; мутация «без явного размера» роняет тест EMU.
- [x] T011 [RT] `pdf_text_layer_import_succeeded` += `images_replaced_by_frame_render`. — **Proof**: тест события.
- [x] T012 `tests/test_pdf_image_frames_corpus.py` (`pytestmark = pytest.mark.integration_local`): Rethinking — опись +
  спаны + план + применение: заменены ровно картинки страниц R20 (32), отказ — 12 на стр. 151 (все `text_over_frame` или
  `image_over_frame`), у каждой замены пикселей ≥ источника. — **Proof**: зелёный.
- [x] T013 `scripts/measure-pdf-image-frames.py`: четыре книги через `_convert_pdf_text_layer_to_docx` с правилом и без
  (подмена плана пустым в процессе): абзацы DOCX (текст, стиль), sha1 картинок по порядку, время; side-by-side «страница |
  выдано» каждой замены в `D:\Temp\claude\work-082\after\`; строка в `scripts/README.md`. — **Proof**: прогон: Money,
  Creating, Value — всё то же; Rethinking — абзацы те же, картинки отличаются ровно в 32 местах R20; не меньше десяти пар
  просмотрены глазами (Read) — запись в Changelog.

## Phase 4: Polish

- [x] T014 [DOC] `docs/LOGGING_AND_ARTIFACT_RETENTION.md` (события по контракту; `pdf_image_extraction_*` из §3.8 в
  описанные; §7), `scripts/_list_log_events.py` `TARGETS` += `images.py`, `image_frames.py`. — **Proof**:
  `tests/test_documentation_links.py`, `tests/test_script_contract_static.py`.
- [x] T015 [DOC] `docs/WORKFLOW_AND_IMAGE_MODES.md` (PDF import: картинка в пространстве краски — отрисовка рамки);
  `AGENTS.md` «Прочее по runtime» (`pypdfium2` из `requirements.txt`). — **Proof**: `tests/test_agent_contract_consistency.py`,
  `tests/test_documentation_links.py`.
- [x] T016 [DOC] `docs/testing/TEST_TIER_INVENTORY.md`: `test_pdf_page_render.py`, `test_pdf_image_frames.py` — Unit-Contract;
  `test_pdf_image_frames_corpus.py` — Integration-Local. — **Proof**: `tests/test_script_contract_static.py`.
- [x] T017 `tests/test_typecheck.py` (timeout ≥ 180000 мс). — **Proof**: зелёный.
- [x] T018 [DOC] `spec.md` Changelog: мутации, числа T012/T013 (sha1 до/после), время, `file:line` итогового кода. —
  **Proof**: `tests/test_spec_status_consistency.py` (кроме проверки строки `WHERE_WE_ARE` — за оркестратором).
- [x] T019 Прогоны отдельными командами: новые тестовые файлы, `tests/test_processing_runtime.py`, `tests/test_logger.py`,
  `tests/test_pdf_text_layer_quality.py`, `tests/test_pdf_text_layer_logical_import.py`, гарды. — **Proof**: счёт
  `passed` дословно.
- [ ] T020 Оркестратор: полный прогон в главном дереве после слияния, `git status --porcelain` пуст, CI ставит колесо.
- [x] T021 Оркестратор: приёмочное ревью Codex по затронутым поверхностям среза A — «ПРИНЯТЬ ПОСЛЕ ПРАВОК»
  (`D:\Temp\claude\076-data\codex_report_082a.txt`).

## Правки по приёмочному ревью среза A (2026-11-13)

Решения — spec Changelog «приёмочное ревью Codex, срез A», research R25–R27.

- [x] T022 `git merge main` в ветку; воспроизвести находки тестами до правки — `tests/test_pdf_image_frames_review.py`
  (12 падают на `84e262ec` + `main`). — **Proof**: `work-082/review_repro_before.txt`.
- [x] T023 [IMG] Матрица размещения картинки в описи (`placement_matrix`). — **Proof**: тест описи.
- [x] T024 `page_render.py`: границы — `read_page_geometry` (pdfminer), рамка только целиком внутри `CropBox`, сверка
  размера и поворота PDFium, растр по числам PDFium. — **Proof**: `tests/test_pdf_page_render.py`.
- [x] T025 `image_frames.py`: триггер — знак корреляции; отказы `unsupported_placement`, `user_unit`,
  `page_geometry_disagrees`, `flat_image`. Замер распределения на корпусе до выбора (R25). — **Proof**:
  `tests/test_pdf_image_frames.py`, `tests/test_pdf_image_frames_review.py`, тест корпуса.
- [x] T026 [RT] Ветка OCR без замен; счётчик доставленных отрисовок. — **Proof**: `test_spec082_no_frame_replacement_in_the_ocr_branch`,
  `test_spec082_success_event_counts_only_renders_that_reached_the_docx`.
- [x] T027 Пространственные проверки на асимметричной картинке во всех тестах замены. — **Proof**: мутация N12 убита.
- [x] T028 `scripts/measure-pdf-image-frames.py run/compare` с полными последовательностями и происхождением; замер «база
  `main` | ветка» на четырёх книгах. — **Proof**: `work-082/after2/compare.json`.
- [x] T029 `scripts/docker-ci-parity.sh` ставит `requirements.txt`; статический тест обновлён. — **Proof**:
  `tests/test_script_contract_static.py`.
- [x] T030 Мутации N1–N19, документы (контракт событий, `LOGGING_AND_ARTIFACT_RETENTION.md` §3.15/§7,
  `WORKFLOW_AND_IMAGE_MODES.md`, `AGENTS.md`, инвентарь тестов), Changelog спеки. — **Proof**: `mutations_review.txt`;
  гарды документов.

## Правки по приёмочному ревью среза A, раунд 2 (2026-11-13)

Решения — spec Changelog «приёмочное ревью Codex, срез A, раунд 2», research R28.

- [x] T031 Воспроизвести находки 1–3 синтетикой до правки — `tests/test_pdf_image_frames_review2.py` на `9c4694d`
  (10 падают, 8 контрольных проходят). — **Proof**: `work-082/review2_repro_before_lines.txt`.
- [x] T032 [IMG] Наблюдающий проход `pdf_import/paint_evidence.py`; в описи — истинная рамка (`frame_box`), маска,
  обтравки, закрашенные контуры и заливки. — **Proof**: `test_the_observed_walk_yields_the_layout_pdfminer_yields`.
- [x] T033 `image_frames.py`: отказы `paint_over_frame`, `masked_image`, `clipped_frame`; сравнение на видимой части
  прямоугольной обтравки; допуск по истинной рамке; сбой кодирования PNG — сбой одной картинки. — **Proof**: тесты
  раунда 2, тест корпуса (31 замена).
- [x] T034 `scripts/measure-pdf-image-frames.py compare`: все поля картинки, добавленные и удалённые хвосты; контракт
  `import-output.md` о docker parity. — **Proof**: `test_the_compare_command_reports_size_only_changes_and_added_or_removed_tails`.
- [x] T035 Замер «база `main` | ветка» на четырёх книгах, десять троек глазами, мутации M1–M17 и повтор N1–N19,
  документы, Changelog спеки. — **Proof**: `work-082/after3/compare.json`, `mutations_round2.txt`,
  `mutations_review_after_round2.txt`.

## Правки по приёмочному ревью среза A, раунд 3 (2026-11-13)

Решение оркестратора — упростить. Решения — spec Changelog «приёмочное ревью Codex, срез A, раунд 3», research R29.

- [x] T036 Удалить наблюдатель краски (`pdf_import/paint_evidence.py`), отказы `paint_over_frame`, `clipped_frame`,
  сужение сравнения; обход картинок — снова `extract_pages`. — **Proof**: `git show --stat`, тесты.
- [x] T037 Триггер «причина И свидетельство»; отказ `not_ink_space`; `/SMask`/`/Mask` из словаря; чтение никогда не
  бросает. — **Proof**: `test_only_an_ink_space_image_is_checked`, `test_cause_half_…`, `test_evidence_half_…`,
  `test_reading_the_image_dictionary_never_raises`, `test_the_cause_is_an_ink_space_indexed_over_one_included`.
- [x] T038 [RT] Сдерживание по стадиям (план, геометрия страницы, рамка, отрисовка, сравнение, кодирование, вставка). —
  **Proof**: `test_spec082_no_failure_in_the_frame_step_changes_what_the_import_delivers`,
  `test_a_failure_in_one_image_is_one_failed_image_and_the_rest_are_still_replaced`,
  `test_a_document_level_failure_keeps_every_image_and_counts_each_as_failed`.
- [x] T039 Замер «`main` | ветка» на четырёх книгах, десять троек глазами (стр. 276 включительно), мутации C1–C13 и
  повтор N1–N18, документы, Changelog. — **Proof**: `work-082/after4/compare.json`, `mutations_round3.txt`,
  `mutations_review_after_round3.txt`.

## Срез B — составная иллюстрация одной картинкой, текст не удаляется (редакция 2026-11-13 по решению владельца D-6)

Решения — spec FR-B1…FR-B13, research R30–R36, plan «Срез B — дизайн». Прежний проект удаления подписей (E1–E7) задач
не получает. Метки: **[FR]** — новый `src/docxaicorrector/pdf_import/figure_regions.py`; **[LI]** —
`pdf_import/logical_import.py` (только вынос функции, согласовать с владельцем ветки, Q-5); остальные — как выше. Тексты
тестов — вымышленные; синтетический PDF — `tests/pdf_synthetic.py` (дополняется: Flate-битмап без файла, путь-кривая,
вложенный `LTFigure`). Каждое условие — тест, падающий при его снятии (мутация; перечень и результат — Changelog, T052).

- [x] T040 Оркестратор: второе ревью дизайна Codex по этой редакции (спека, план, исследование R30–R36, модель данных,
  контракты, задачи; данные `D:\Temp\claude\work-082b\`). Находки — в Changelog до T041. — **Proof**:
  `D:\Temp\claude\076-data\codex_report_082Bdesign.txt` («СТРОИТЬ ПОСЛЕ ПРАВОК ПРОЕКТА»), Changelog «ревью дизайна
  среза B, раунд 2».
- [x] T041 [IMG] `PdfImageObject.region_members: tuple[PdfImageObject, ...] | None = None` — `None` обычная картинка,
  `()` область без выданных членов (N = 0), непустой кортеж — область с членами; пиклится; прочий код не меняется. —
  **Proof**: тест пикла для `None`, `()` и непустого кортежа; `tests/test_processing_runtime.py` зелёный без правок.
- [x] T042 [LI] Общая подготовка профиля: `_prepare_spans_for_import(spans)` (нормализация, повторяющиеся колонтитулы,
  колонтитулы на строке номера, сортировка, профиль — всё, что строки `:152-176` готовят для импортёра) и публичная
  `pdf_body_typography(spans) -> PdfBodyTypography`; `build_paragraph_units_from_text_spans` вызывает ту же подготовку;
  литерал `7` строки тела (`:777`) получает имя `_BODY_LINE_MIN_WORDS`. Правка минимальна и локальна (тот же модуль
  параллельно меняет ветка распознавания заголовков). — **Proof**: `tests/test_pdf_text_layer_logical_import.py` без
  изменений; тест «функция = профиль импортёра» на синтетике с колонтитулом; абзацы четырёх книг — T051.
- [x] T043 [FR] `read_page_graphics(pdf_path, pages)` — отдельный pdfminer-проход, `LTImage` (порядок обхода
  извлекателя, `srcsize`) и `LTCurve` внутри `LTFigure`, рамка пути по всем операндам `original_path`. — **Proof**:
  синтетика (кривая с опорной точкой вне концов — рамка её содержит; путь во вложенной форме виден; `discovery_index`
  совпадает с описью); мутации «рамка по концам» и «без `LTFigure`» роняют тесты.
- [x] T044 [FR] `plan_figure_regions` — чистое правило на рамках (`tests/test_pdf_figure_regions.py`, без PDF): связь при
  зазоре = допуску / нет при чуть большем; семя только непередаваемое (страница без семени — пустой план); охватывающий
  путь (рамка полосы вокруг большинства строк) — не связывает; охватывающая картинка — отказ `image_encloses_page_text`;
  рост по компоненте, касающейся рамки; рост по строке мельче тела на краю графики и НЕ по следующей строке блока; строка
  кегля тела на краю — G1; G1 с буквой, с одними цифрами; строка-символ крупного кегля — не отказ; G2 полная мелкая строка;
  касание нулевой площади — не отказ; T1 профиль неизвестен; T2 связный текст вне области не кеглем тела (профиль 12 pt,
  страница 8 pt); T3 текстовый блок в рамке со значком; слияние касающихся областей; две раздельные схемы — две области;
  выдаваемая картинка, задевающая край, — член целиком; `CropBox` — обрезка, пустое → `outside_crop_box`; член частично
  вне `CropBox` с каждой из четырёх сторон → `member_outside_crop_box`; расхождение описи → `inventory_mismatch`; допуск
  без текста — медиана книги; одиночное семя (N = 0) — область с `member_keys = ()`. — **Proof**: тесты; мутация на
  каждое условие.
- [x] T045 [FR] Применение: плотность = max(наибольшая плотность выданных членов после среза A, взвешенная медиана
  семян), N = 0 — медиана семян, нет пикселей — `unknown_density`; `read_page_geometry`/`frame_geometry`/бюджет/
  `render_frame`/`encode_frame_png`; атомарность страницы; события. — **Proof**: `tests/test_pdf_figure_regions_render.py`
  на синтетике: картинка области = отрисовка страницы в рамке (асимметричный маркер на месте); исправный член с мелким
  шаблоном (плотность выше семени) — в картинке области не меньше его пикселей на его рамке; две области, сбой второй →
  ни одной; бюджет → отказ; `/UserUnit` → отказ; N = 0 → одна новая картинка с явным размером.
- [x] T046 [RT] `_run_pdf_parse_stages`: лимит на выданном списке до шагов; срез A без изменений; области на его выходе
  (`figure_regions.replace_composite_figures`, сдержано); итог сверх лимита → отказ шага B целиком; OCR — не вызывается;
  ОДНО итоговое событие после обоих шагов с прежними ключами, `frame_render_*` и `figure_region_*`. — **Proof**: тест
  лимита до шагов; тест «итог B сверх лимита — выход A»; шпион OCR; тест корпуса среза A и `tests/test_pdf_image_frames*.py`
  — зелёные.
- [x] T047 [RT] Сборка DOCX как транзакция: картинка области вставляется с явным размером; сбой вставки любой области →
  все области её страницы заменяются членами, документ собирается заново с начала; `images_emitted` — картинки
  окончательного документа; `figure_regions_inserted`, `figure_region_members_restored`; ERROR
  `pdf_figure_region_insert_failed`. — **Proof**: сбой вставки первой и (отдельно) второй области одной страницы →
  последовательность абзацев и картинок DOCX (sha1, EMU, позиции) равна сборке без шага; счётчики равны фактическим;
  EMU области = рамка × 12700.
- [x] T048 [RT] Сдерживание по стадиям — тест-таблица по образцу
  `test_spec082_no_failure_in_the_frame_step_changes_what_the_import_delivers`: `inventory`, `typography`, `plan`,
  `page_geometry`, `render`, `encode`, `step`, вставка первой области, вставка второй области страницы — документ равен
  прогону без шага (те же картинки на тех же местах, те же абзацы), ERROR со стадией. — **Proof**: тест; мутация «не
  ловить» на стадии роняет её строку.
- [x] T049 [RT] Инвариант текста FR-B7 и соседство: синтетика с областью — `parse_result.spans` тот же список, абзацы
  DOCX равны прогону без шага (мутация «отбросить спан внутри области»); синтетика, где N картинок между короткими
  абзацами становятся одной, — абзацы после `_prepare_document_for_processing` (текст, роль, граница, подпись) равны
  прогону без шага, кроме строк-картинок; картинка, заменённая срезом A и поглощённая областью, при откате доставки
  возвращается заменённой (байты и размер среза A). — **Proof**: тесты.
- [x] T050 `tests/test_pdf_figure_regions_corpus.py` (`integration_local`, Rethinking): одна область, стр. 151, рамка
  `[42,2; 68,2; 353,8; 499,5]` ± 0,1, 22 выдаваемых члена, 261 семя, 2365 путей, 2 строки роста; других областей нет. —
  **Proof**: зелёный; без книги — `skip` (запись в Changelog, что CI его не подтверждает).
- [x] T051 `scripts/measure-pdf-image-frames.py`: провенанс «есть ли шаг областей»; side-by-side картинки области
  «члены | область | страница»; опция подготовки аудиокниги (роль, причина, текст). Замер «`main` | ветка» на четырёх
  книгах. — **Proof**: SC-B1, SC-B2 (0 различий абзацев; Rethinking 55 → 34, позиции 18–39; 2603 абзаца подготовки);
  картинка области и Ghostscript со сглаживанием — глазами (Read), запись в Changelog.
- [x] T052 [DOC] `docs/LOGGING_AND_ARTIFACT_RETENTION.md` (события среза B, §7), `scripts/_list_log_events.py` `TARGETS`
  += `figure_regions.py`, `docs/WORKFLOW_AND_IMAGE_MODES.md` (PDF import: составная иллюстрация — одна картинка, подписи
  остаются абзацами), `docs/testing/TEST_TIER_INVENTORY.md` (три новых файла), Changelog спеки: мутации, числа, `file:line`.
  — **Proof**: `tests/test_documentation_links.py`, `tests/test_script_contract_static.py`,
  `tests/test_agent_contract_consistency.py`, `tests/test_spec_status_consistency.py`.
- [x] T053 Прогоны отдельными командами: новые файлы, `tests/test_processing_runtime.py`, `tests/test_pdf_image_frames*.py`,
  `tests/test_pdf_page_render.py`, `tests/test_pdf_text_layer_logical_import.py`, `tests/test_logger.py`, гарды,
  `tests/test_typecheck.py` (≥ 180000 мс). — **Proof**: счёт `passed` дословно.
- [ ] T054 Оркестратор: полный прогон в главном дереве после слияния, `git status --porcelain` пуст; приёмочное ревью
  Codex по затронутым поверхностям (`figure_regions.py`, `images.py`, `logical_import.py`, `processing_runtime.py`,
  `page_render.py`, `image_frames.py`, тесты, скрипт). — **Proof**: отчёт `docs/reviews/CODEX_REVIEW_082B_<дата>.md`.

## Сводка

Срез A: 39 задач (Setup 3, Foundational 1, срез A 9, Polish 8, правки ревью 9, раунда 2 — 5, раунда 3 — 4). **[RT]**:
T003, T004, T009–T011, T026, T038. **[IMG]**: T004, T023, T032. **[REQ]**: T001. **[DOC]**: T014–T016, T018, T030, T035.
Срез B: 15 задач T040–T054 (ревью дизайна 1, модель и типографика 2, опись 1, правило 1, применение 1, мост 4, корпус и
замер 2, документы и прогоны 2, оркестратор 1). **[RT]**: T046–T049. **[FR]**: T043–T045. **[IMG]**: T041. **[LI]**: T042.
**[DOC]**: T052.
