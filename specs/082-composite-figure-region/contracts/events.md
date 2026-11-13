# Contract: события картинок PDF (срез A) и итог извлечения

**Spec**: [../spec.md](../spec.md) FR-A9, FR-A10 | **Date**: 2026-11-13 (раунд 2)

События отрисовки пишет дочерний процесс разбора (`processing_runtime.py:705-791`); при прогоне раннера они попадают в
`<run_dir>/app.log` через `DOCX_AI_RUN_LOG_FILE` (`docs/LOGGING_AND_ARTIFACT_RETENTION.md` §1.1). Событие вставки пишет
родитель при сборке DOCX. Текст книги — только начало ≤ 120 знаков (§4 п. 5). Имена проверены на отсутствие в каталоге §3
и в `src/` (2026-11-13).

## `pdf_image_frame_rendered` — INFO, одно на заменённую картинку

| Ключ | Тип | Смысл |
|---|---|---|
| `pdf_path` | str | как у `pdf_image_extraction_summary` |
| `page_number`, `discovery_index` | int | ключ картинки |
| `box` | [float×4] | рамка размещения, pt, 1 знак |
| `colour_space` | str | семейство (`Separation` / `DeviceN`) |
| `source_width_px`, `source_height_px` | int | пиксели источника |
| `width_px`, `height_px` | int | пиксели отрисовки (≥ источника) |
| `scale_dpi` | float | плотность отрисовки |
| `bytes` | int | размер PNG |
| `grayscale` | bool | PNG в оттенках серого |

## `pdf_image_frame_render_declined` — INFO, одно на картинку-кандидата без замены

`pdf_path`, `page_number`, `discovery_index`, `box`, `colour_space`, `reason` (`text_over_frame` | `image_over_frame` |
`exceeds_pixel_budget` | `outside_crop_box`), `detail` (≤ 120 знаков: начало строки поверх рамки или ключ другой
картинки). INFO: отказ — штатный исход, картинка остаётся как сегодня.

## `pdf_image_frame_render_failed` — ERROR, одно на картинку, отрисовка которой бросила исключение

`pdf_path`, `page_number`, `discovery_index`, `box`, `error_type`, `error_message` (≤ 120). Картинка остаётся с исходными
байтами. ERROR — дефект кода или входа; уведомления в интерфейсе нет.

## `pdf_image_replacement_insert_failed` — ERROR, родитель, при сбое вставки PNG-замены в DOCX

`source_index`, `page_number`, `error_type`, `error_message` (≤ 120), `fallback_inserted` (bool — удалось ли вставить
исходные байты прежним путём). Если не удалось и исходное — дальше прежнее `pdf_text_layer_image_render_dropped`.

## `pdf_image_extraction_summary` / `pdf_image_extraction_dropped_images` — изменение

Эмитится ОДИН раз после шага замен (функция `images.py`, вызов из `_run_pdf_parse_stages`), раньше — внутри извлекателя.
Смысл прежних ключей не меняется:

| Ключ | Смысл |
|---|---|
| `discovered`, `emitted`, `skipped`, `skipped_no_image_bytes`, `skipped_unknown_mime`, `pages_truncated` | как сегодня (`images.py:99-125`); выводятся из `skip_reason` описи |
| `frame_render_replaced` | новое: заменено отрисовкой рамки |
| `frame_render_declined` | новое: кандидатов без замены |
| `frame_render_failed` | новое: сбоев отрисовки |

Уровень — как сегодня: WARNING `pdf_image_extraction_dropped_images` при `skipped > 0`, иначе INFO
`pdf_image_extraction_summary`. Ожидаемо: Rethinking — WARNING, `discovered 316, emitted 55, skipped 261,
frame_render_replaced 32, frame_render_declined 12, frame_render_failed 0`; Money / Creating / Value — INFO, новые
счётчики 0.

## `pdf_text_layer_import_succeeded` — один новый ключ

`images_replaced_by_frame_render` — число картинок-замен в итоговом списке (родитель считает по
`original_image_bytes is not None`); `images_emitted` — вставленные в DOCX, как раньше.

## Документы

- `docs/LOGGING_AND_ARTIFACT_RETENTION.md`: `pdf_image_extraction_*` — из §3.8 в описанные; четыре новых события —
  подразделом «Спека 082: картинки PDF как на странице»; запись в §7.
- `scripts/_list_log_events.py`: `TARGETS` += `src/docxaicorrector/pdf_import/images.py`,
  `src/docxaicorrector/pdf_import/image_frames.py`.
