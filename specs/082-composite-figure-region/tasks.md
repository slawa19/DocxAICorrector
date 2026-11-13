# Tasks: картинки PDF — такими, какими их видит читатель страницы

**Spec**: [spec.md](spec.md) | **Plan**: [plan.md](plan.md) | **Контракты**: [contracts/](contracts/) |
**Данные**: [data-model.md](data-model.md), [research.md](research.md) | **Проверка**: [quickstart.md](quickstart.md)

Tier: полный цикл (Конституция III). Раунд 2 (после ревью дизайна): задачи — только для **среза A**; задачи среза B
пишутся после ревью дизайна раунда 2 и решения Q-4. Задачи идут по порядку одним исполнителем; внутри задачи: падающий
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

- [ ] T001 [REQ] `pypdfium2==5.15.2` в `requirements.txt` и `[project.optional-dependencies].pdf-import` `pyproject.toml`;
  `scripts/setup-wsl.sh` `verify_runtime` импортирует `pdfminer`, `pypdfium2`. — **Proof**:
  `tests/test_script_contract_static.py`; `python -I -c "import pypdfium2"`.
- [ ] T002 `tests/pdf_synthetic.py`: сборщик PDF байтами — страница (`MediaBox`, `CropBox`, `/Rotate`), JPEG в `DeviceGray`
  и в `Separation` (Pillow), Flate-битмап, обводимый путь, залитый прямоугольник, строка Helvetica заданного кегля. —
  **Proof**: смоук-тест в `tests/test_pdf_page_render.py` (pdfminer видит спаны и `LTImage`, pypdfium2 рисует).
- [ ] T003 [RT] Характеристика ДО правки: мост `_convert_pdf_text_layer_to_docx` на синтетике без триггера (JPEG
  `DeviceGray` между абзацами) — тексты абзацев, порядок, sha1 картинки — в `tests/test_processing_runtime.py`. —
  **Proof**: зелёный на базе и после каждой следующей задачи без правки.

## Phase 2: Foundational

- [ ] T004 [IMG] [RT] `images.py`: `PdfDiscoveredImage`, `PdfImageExtraction`, новые поля `PdfImageObject`,
  `extract_pdf_images_and_inventory`, `log_pdf_image_extraction_outcome` (прежние ключи + нулевые новые);
  `extract_pdf_images_with_pdfminer` и её экспорт удалены; `_run_pdf_parse_stages` вызывает новую точку входа (поведение
  прежнее); подмены в `tests/test_processing_runtime.py` переведены. — **Proof**: новые тесты описи (ключ, семейство,
  `skip_reason`, одинаковые `discovery_index` на разных страницах — разные ключи) и `tests/test_processing_runtime.py`
  целиком; T003.

## Phase 3: Срез A (US1)

- [ ] T005 `pdf_import/page_render.py`: `layout_cropbox`, `frame_geometry` (чистые) — тесты в `tests/test_pdf_page_render.py`:
  округление наружу (пикселей ≥ `w_pt·scale`, `h_pt·scale`), сдвиг `CropBox`, частично вне `CropBox`, целиком вне → `None`,
  поворот 0/90/180/270, фактическая рамка в pt. — **Proof**: тесты; мутация «без округления наружу» роняет тест пикселей.
- [ ] T006 `page_render.render_frames` (pypdfium2, замок, PNG `L`/`RGB`, `pHYs`) — тесты на синтетике: чёрный квадрат на
  странице с `CropBox ≠ MediaBox` и с `/Rotate 90` — в отрисовке рамки, найденной pdfminer, на ожидаемых пикселях; серая
  страница → `L`; цветная → `RGB`; пустой запрос не открывает документ. — **Proof**: тесты; мутация «без `CropBox`» роняет
  тест квадрата.
- [ ] T007 `pdf_import/image_frames.py`: `colour_space_is_ink`, `plan_frame_replacements` — тесты в
  `tests/test_pdf_image_frames.py`: `Separation` и `DeviceN` — кандидаты; `DeviceGray`, `DeviceRGB`, `ICCBased`, `Indexed`,
  `None` — нет; строка поверх рамки → `text_over_frame`; строка, касающаяся рамки краем (нулевая площадь), — не отказ;
  другая картинка поверх → `image_over_frame`; масштаб = плотность источника. — **Proof**: тесты; мутации (снять проверку
  семейства / отказ по тексту / отказ по картинке) роняют каждая свой тест.
- [ ] T008 `image_frames.apply_frame_replacements` и события (contracts/events.md) — тесты: замена несёт PNG, `display_*`,
  `original_*`, тот же `source_index`/рамку/ключ; пикселей не меньше источника; `exceeds_pixel_budget` (подмена
  потолка); сбой отрисовки → исходные байты + ERROR; события с ключами контракта. — **Proof**: тесты.
- [ ] T009 [RT] `_run_pdf_parse_stages`: опись → план → замены → итоговое событие → лимит; исключение шага замен →
  исходные картинки + ERROR. Сквозной тест моста: JPEG `Separation` между абзацами → в DOCX картинка, средняя яркость
  которой как у страницы (не как у инверсии); спаны и абзацы те же; итог WARNING/INFO с новыми счётчиками. — **Proof**:
  тесты; T003 зелёный.
- [ ] T010 [RT] `_append_image_bytes_to_docx(document, bytes, width_pt=None, height_pt=None)`; замена — с явным размером;
  сбой вставки замены → исходные байты прежним путём + ERROR `pdf_image_replacement_insert_failed`. Тесты: EMU = рамка ×
  12700 на дробной плотности (217,5 dpi) и на рамке, обрезанной `CropBox`; подмена `add_picture` исключением для PNG →
  исходный JPEG в DOCX + ERROR. — **Proof**: тесты; мутация «без явного размера» роняет тест EMU.
- [ ] T011 [RT] `pdf_text_layer_import_succeeded` += `images_replaced_by_frame_render`. — **Proof**: тест события.
- [ ] T012 `tests/test_pdf_image_frames_corpus.py` (`pytestmark = pytest.mark.integration_local`): Rethinking — опись +
  спаны + план + применение: заменены ровно картинки страниц R20 (32), отказ — 12 на стр. 151 (все `text_over_frame` или
  `image_over_frame`), у каждой замены пикселей ≥ источника. — **Proof**: зелёный.
- [ ] T013 `scripts/measure-pdf-image-frames.py`: четыре книги через `_convert_pdf_text_layer_to_docx` с правилом и без
  (подмена плана пустым в процессе): абзацы DOCX (текст, стиль), sha1 картинок по порядку, время; side-by-side «страница |
  выдано» каждой замены в `D:\Temp\claude\work-082\after\`; строка в `scripts/README.md`. — **Proof**: прогон: Money,
  Creating, Value — всё то же; Rethinking — абзацы те же, картинки отличаются ровно в 32 местах R20; не меньше десяти пар
  просмотрены глазами (Read) — запись в Changelog.

## Phase 4: Polish

- [ ] T014 [DOC] `docs/LOGGING_AND_ARTIFACT_RETENTION.md` (события по контракту; `pdf_image_extraction_*` из §3.8 в
  описанные; §7), `scripts/_list_log_events.py` `TARGETS` += `images.py`, `image_frames.py`. — **Proof**:
  `tests/test_documentation_links.py`, `tests/test_script_contract_static.py`.
- [ ] T015 [DOC] `docs/WORKFLOW_AND_IMAGE_MODES.md` (PDF import: картинка в пространстве краски — отрисовка рамки);
  `AGENTS.md` «Прочее по runtime» (`pypdfium2` из `requirements.txt`). — **Proof**: `tests/test_agent_contract_consistency.py`,
  `tests/test_documentation_links.py`.
- [ ] T016 [DOC] `docs/testing/TEST_TIER_INVENTORY.md`: `test_pdf_page_render.py`, `test_pdf_image_frames.py` — Unit-Contract;
  `test_pdf_image_frames_corpus.py` — Integration-Local. — **Proof**: `tests/test_script_contract_static.py`.
- [ ] T017 `tests/test_typecheck.py` (timeout ≥ 180000 мс). — **Proof**: зелёный.
- [ ] T018 [DOC] `spec.md` Changelog: мутации, числа T012/T013 (sha1 до/после), время, `file:line` итогового кода. —
  **Proof**: `tests/test_spec_status_consistency.py` (кроме проверки строки `WHERE_WE_ARE` — за оркестратором).
- [ ] T019 Прогоны отдельными командами: новые тестовые файлы, `tests/test_processing_runtime.py`, `tests/test_logger.py`,
  `tests/test_pdf_text_layer_quality.py`, `tests/test_pdf_text_layer_logical_import.py`, гарды. — **Proof**: счёт
  `passed` дословно.
- [ ] T020 Оркестратор: полный прогон в главном дереве после слияния, `git status --porcelain` пуст, CI ставит колесо.
- [ ] T021 Оркестратор: приёмочное ревью Codex по затронутым поверхностям среза A.

## Срез B

Задачи не пишутся до ревью дизайна раунда 2 (spec FR-B1…FR-B8, research R23–R24, Q-4). Перечень контрпримеров, которые
задачи обязаны покрыть, — spec «Anti-regression», срез B.

## Сводка

Срез A: 21 задача (Setup 3, Foundational 1, срез A 9, Polish 8). **[RT]**: T003, T004, T009–T011. **[IMG]**: T004.
**[REQ]**: T001. **[DOC]**: T014–T016, T018.
