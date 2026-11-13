# Contract: события картинок PDF (срез A) и итог извлечения

**Spec**: [../spec.md](../spec.md) FR-A9, FR-A10 | **Date**: 2026-11-13 (раунд 3 приёмочного ревью)

События отрисовки пишет дочерний процесс разбора (`processing_runtime.py:705-791`); при прогоне раннера они попадают в
`<run_dir>/app.log` через `DOCX_AI_RUN_LOG_FILE` (`docs/LOGGING_AND_ARTIFACT_RETENTION.md` §1.1). Событие вставки пишет
родитель при сборке DOCX. Текст книги — только начало ≤ 120 знаков (§4 п. 5). Имена проверены на отсутствие в каталоге §3
и в `src/` (2026-11-13).

## `pdf_image_frame_rendered` — INFO, одно на заменённую картинку

| Ключ | Тип | Смысл |
|---|---|---|
| `pdf_path` | str | как у `pdf_image_extraction_summary` |
| `page_number`, `discovery_index` | int | ключ картинки |
| `box` | [float×4] | рамка размещения, pt, 1 знак; истинная, не прижатая к странице (раунд 2 ревью, находка 2) |
| `colour_space` | str | семейство цветового пространства; у заменённой — пространство краски (причина, раунд 3) |
| `correlation` | float | коэффициент корреляции картинки с отрисовкой рамки (< 0 — негатив), 4 знака |
| `source_width_px`, `source_height_px` | int | пиксели источника |
| `width_px`, `height_px` | int | пиксели отрисовки (≥ источника) |
| `scale_dpi` | float | плотность отрисовки |
| `bytes` | int | размер PNG |
| `grayscale` | bool | PNG в оттенках серого |

## `pdf_image_frame_render_declined` — INFO, одно на выданную картинку, которую не сравнили или не заменили по отказу

`pdf_path`, `page_number`, `discovery_index`, `box`, `colour_space`, `reason`, `detail` (≤ 120 знаков: начало строки поверх
рамки, ключ другой картинки, матрица размещения или текст расхождения движков). `reason` ∈ `text_over_frame`,
`image_over_frame`, `masked_image` (в словаре картинки `/SMask` или `/Mask`; `detail` — какой, или `unreadable`, если
словарь не читается), `not_ink_space` (пространство не `Separation`/`DeviceN` и не `Indexed` над ними: причины для
замены нет; раунд 3), `unsupported_placement` (размещение — не прямой масштаб), `unreadable_source` (заголовок файла не
читается или рамка пуста), `user_unit` (`/UserUnit` ≠ 1), `outside_crop_box` (рамка не целиком внутри `CropBox`),
`exceeds_pixel_budget`, `page_geometry_disagrees` (pdfminer и PDFium по-разному меряют страницу), `flat_image` (нет
разброса яркости). INFO: отказ — штатный исход, картинка остаётся как сегодня. Картинка, сравнённая и похожая на свою
страницу (r ≥ 0), события не порождает — её считает `frame_render_checked`.

## `pdf_image_frame_render_failed` — ERROR, одно на картинку, рамка, отрисовка, сравнение или кодирование которой бросили исключение

`pdf_path`, `page_number`, `discovery_index`, `box`, `error_type`, `error_message` (≤ 120). Картинка остаётся с исходными
байтами, остальные картинки обрабатываются дальше (до раунда 2 ревью сбой кодирования PNG прерывал весь план и не
считался). ERROR — дефект кода или входа; уведомления в интерфейсе нет.

## `pdf_image_replacement_insert_failed` — ERROR, родитель, при сбое вставки PNG-замены в DOCX

`source_index`, `page_number`, `error_type`, `error_message` (≤ 120), `fallback_inserted` (bool — удалось ли вставить
исходные байты прежним путём). Если не удалось и исходное — дальше прежнее `pdf_text_layer_image_render_dropped`.

## `pdf_image_extraction_summary` / `pdf_image_extraction_dropped_images` — изменение

Эмитится ОДИН раз после шага замен (функция `images.py`, вызов из `_run_pdf_parse_stages`), раньше — внутри извлекателя.
Смысл прежних ключей не меняется:

| Ключ | Смысл |
|---|---|
| `discovered`, `emitted`, `skipped`, `skipped_no_image_bytes`, `skipped_unknown_mime`, `pages_truncated` | как сегодня (`images.py:99-125`); выводятся из `skip_reason` описи |
| `frame_render_enabled` | новое: `false` в ветке OCR (шаг не работает, FR-A14) |
| `frame_render_checked` | новое: картинок, сравнённых со своей отрисовкой |
| `frame_render_replaced` | новое: заменено отрисовкой рамки (r < 0) |
| `frame_render_declined` | новое: отказов (до сравнения и после: плоская картинка) |
| `frame_render_failed` | новое: сбоев отрисовки |

Уровень — как сегодня: WARNING `pdf_image_extraction_dropped_images` при `skipped > 0`, иначе INFO
`pdf_image_extraction_summary`. Ожидаемо на корпусе: Rethinking — WARNING, `discovered 316, emitted 55, skipped 261,
frame_render_checked 32, frame_render_replaced 32, frame_render_declined 23, frame_render_failed 0` (тест корпуса;
отказы — 22 картинки стр. 151 и обложка `not_ink_space`); Money — INFO, сравнено 0, отказов 43 (текст 1,
`not_ink_space` 42); Creating — сравнено 0, отказов 62 (текст 7, `not_ink_space` 55); Value — сравнено 0, отказов 42
(`masked_image` 10, `not_ink_space` 32); заменено 0 во всех трёх (research R29, `work-082/round3_probe.json`).

## `pdf_text_layer_import_succeeded` — один новый ключ

`images_replaced_by_frame_render` — число отрисовок, реально вставленных в DOCX (откат к выданным байтам не считается);
`images_emitted` — вставленные в DOCX картинки, как раньше.

## Документы

- `docs/LOGGING_AND_ARTIFACT_RETENTION.md`: `pdf_image_extraction_*` — из §3.8 в описанные; четыре новых события —
  подразделом «Спека 082: картинки PDF как на странице»; запись в §7.
- `scripts/_list_log_events.py`: `TARGETS` += `src/docxaicorrector/pdf_import/images.py`,
  `src/docxaicorrector/pdf_import/image_frames.py`.

## Срез B (ДИЗАЙН, редакция 2026-11-13 по решению владельца D-6; не построено)

Имена проверены на отсутствие в `src/` и в каталоге `docs/LOGGING_AND_ARTIFACT_RETENTION.md` §3 (2026-11-13). Текст
книги — только начало ≤ 120 знаков.

### `pdf_figure_region_rendered` — INFO, дочерний процесс, одно на картинку области

`pdf_path`, `page_number`, `box` (рамка области, pt, 1 знак), `seed_count`, `image_count`, `path_count`,
`members_emitted` (выданных картинок внутри), `member_keys` (`[[page, discovery_index], …]`), `absorbed_frame_renders`
(из членов — уже заменённых срезом A), `grown_line_count`, `scale_dpi`, `width_px`, `height_px`, `bytes`, `grayscale`.

### `pdf_figure_region_declined` — INFO, одно на отказанную область (или страницу целиком)

`pdf_path`, `page_number`, `box` (или `null`), `seed_count`, `reason` ∈ `running_text_inside` (G1), `full_line_inside`
(G2), `inventory_mismatch`, `outside_crop_box`, `user_unit`, `page_geometry_disagrees`, `exceeds_pixel_budget`,
`page_atomic` (другая область этой страницы отказала или упала — FR-B8), `detail` (≤ 120: начало строки-стража или
текст расхождения). INFO: страница остаётся как сегодня.

### `pdf_figure_region_failed` — ERROR, дочерний процесс

`pdf_path`, `page_number` (`null` для стадий уровня документа), `stage` ∈ `inventory`, `typography`, `plan`,
`page_geometry`, `frame`, `render`, `encode`, `step`, `error_type`, `error_message` (≤ 120). Исход — страница (или все
страницы для `inventory`, `typography`, `plan`, `step`) как без шага.

### `pdf_figure_region_insert_failed` — ERROR, родитель

`page_number`, `regions` (картинок областей этой страницы), `members_restored` (их членов, вернувшихся на свои места),
`error_type`, `error_message` (≤ 120). Сборка документа после этого повторяется с начала (FR-B10); прежняя редакция
этого пункта: `source_index`, `stage` ∈ `probe` (до сборки: область заменена членами на их местах), `insert` (в сборке:
члены вставлены прежним путём на месте области), `members`, `members_inserted`, `error_type`, `error_message` (≤ 120).

### Итог `pdf_image_extraction_summary` / `pdf_image_extraction_dropped_images` — новые ключи

| Ключ | Смысл |
|---|---|
| `figure_region_enabled` | `false` в ветке OCR (FR-B11) |
| `figure_region_seed_pages` | страниц с непередаваемой картинкой |
| `figure_region_rendered` | картинок областей в выходе разбора |
| `figure_region_declined` | отказанных областей |
| `figure_region_failed` | сбоев (страниц) |
| `figure_region_images_absorbed` | выданных картинок, ушедших в области |

Прежние ключи и счётчики среза A — без изменений (срез A работает до областей на всех выданных картинках, FR-B9).
Ожидаемо на корпусе (research R34): Rethinking — `figure_region_seed_pages 1, rendered 1, declined 0, failed 0,
images_absorbed 22`; `frame_render_*` — как сегодня (32 / 32 / 23 / 0); Money, Creating, Value — все `figure_region_*` 0.

### `pdf_text_layer_import_succeeded` — один новый ключ

`figure_regions_inserted` — картинок областей, реально вставленных в DOCX (откат к членам не считается); `image_count` —
длина итогового списка (на Rethinking 55 → 34), `images_emitted` — вставленные картинки, как раньше.

### Документы

`docs/LOGGING_AND_ARTIFACT_RETENTION.md` — подраздел «Спека 082, срез B: составная иллюстрация одной картинкой» и
запись в §7; `scripts/_list_log_events.py` `TARGETS` += `src/docxaicorrector/pdf_import/figure_regions.py`.

### Правки после ревью дизайна среза B, раунд 2 (2026-11-13)

- `pdf_figure_region_declined.reason` дополнительно ∈ `image_encloses_page_text`, `typography_unknown` (T1),
  `typography_disagrees` (T2), `text_block_inside` (T3), `member_outside_crop_box`, `unknown_density`,
  `image_count_cap` (итог шага B превысил бы лимит картинок — шаг отказывает целиком).
- `pdf_figure_region_failed.stage` ∈ `inventory`, `typography`, `plan`, `page_geometry`, `render`, `encode`, `step`;
  стадии `probe` нет.
- `pdf_figure_region_rendered` дополнительно: `scale_source` ∈ `member`, `seeds` — чья плотность задала отрисовку.
- Итоговое событие `pdf_image_extraction_*` пишется ОДИН раз — после шага B (до спеки B его писал шаг среза A).
- `pdf_text_layer_import_succeeded`: `images_emitted` — картинки окончательного DOCX после всех откатов (восстановленные
  члены считаются каждый), `figure_regions_inserted`, `figure_region_members_restored`.
