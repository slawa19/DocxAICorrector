# Contract: события областей иллюстраций и итог извлечения картинок PDF

**Spec**: [../spec.md](../spec.md) FR-012 | **Date**: 2026-11-13

Все события пишет дочерний процесс разбора (`processing_runtime.py:705-791`); при прогоне раннера они попадают в
`<run_dir>/app.log` через `DOCX_AI_RUN_LOG_FILE` (`docs/LOGGING_AND_ARTIFACT_RETENTION.md` §1.1). Уровни — по §2
документа логирования. Текст книги в событиях — только начало ≤ 120 знаков (§4 п. 5). Имена проверены на отсутствие в
каталоге §3 и в `src/` (2026-11-13).

## `pdf_figure_region_rendered` — INFO, одно на принятую область

| Ключ | Тип | Смысл |
|---|---|---|
| `filename` | str | имя загрузки (как у `pdf_import_over_budget`) |
| `page_number` | int | 1-based |
| `box` | [float×4] | рамка области, pt, 1 знак после запятой |
| `seed_kind` | str | `non_emittable` \| `ink_space` |
| `resolution_dpi` | float | после потолка FR-008 |
| `width_px`, `height_px` | int | размер PNG |
| `bytes` | int | размер PNG |
| `grayscale` | bool | PNG в оттенках серого |
| `images_absorbed` | int | все картинки области |
| `images_absorbed_emittable` | int | из них те, что вышли бы отдельно |
| `paths_absorbed` | int | пути области |
| `lines_suppressed` | int | строк убрано из текста |
| `chars_suppressed` | int | их знаков |
| `suppressed_preview` | str | начало описания картинки, ≤ 120 знаков |

## `pdf_figure_region_declined` — INFO, одно на отклонённую область

| Ключ | Тип | Смысл |
|---|---|---|
| `filename`, `page_number`, `box`, `seed_kind` | | как выше |
| `reason` | str | `body_size_text` (G1) \| `full_measure_line` (G2); при обоих — `body_size_text` |
| `blocking_text_preview` | str | начало строки-причины, ≤ 120 знаков |
| `images_kept` | int | картинок области, оставшихся как сегодня |

INFO, а не WARNING: отказ — штатный исход правила (страница остаётся как до спеки), не деградация.

## `pdf_figure_region_render_failed` — ERROR, одно на область, которую не удалось отрисовать

| Ключ | Тип | Смысл |
|---|---|---|
| `filename`, `page_number`, `box` | | как выше |
| `error_type` | str | класс исключения |
| `error_message` | str | `str(exc)`, ≤ 120 знаков |

Страница остаётся как до спеки (FR-011). ERROR — потому что это дефект кода или входа, который надо чинить; в
интерфейсе уведомления нет.

## `pdf_image_extraction_summary` / `pdf_image_extraction_dropped_images` — изменение

Сегодня эмитятся внутри извлекателя (`pdf_import/images.py:99-125`) до правила областей и считают «пропущенной» каждую
неотдаваемую картинку — на Rethinking это 261 WARNING-«потеря», хотя после спеки они на картинке области. После
спеки событие эмитится ОДИН раз, после областей (функция в `images.py`, вызов из `_run_pdf_parse_stages`), и:

| Ключ | Было | Стало |
|---|---|---|
| `discovered` | все `LTImage` | то же |
| `emitted` | отдаваемые | картинки, ушедшие в DOCX: отдельные + картинки областей |
| `skipped` | `discovered − emitted` | картинки, не ушедшие никуда: `discovered − absorbed − standalone` |
| `skipped_no_image_bytes`, `skipped_unknown_mime` | | только по неушедшим |
| `figure_regions_rendered` | — | новое |
| `figure_regions_declined` | — | новое |
| `figure_regions_failed` | — | новое |
| `figure_region_images_absorbed` | — | новое |
| `figure_region_paths_absorbed` | — | новое |
| `figure_region_lines_suppressed` | — | новое |
| `figure_region_chars_suppressed` | — | новое |
| `pages_truncated` | | то же |

Уровень: WARNING `pdf_image_extraction_dropped_images`, когда `skipped > 0` (картинка потеряна), иначе INFO
`pdf_image_extraction_summary` — тот же принцип, что сейчас.

Ожидаемо на корпусе (`research.md` R17): Rethinking US1 — `discovered 316, emitted 34, skipped 0,
figure_regions_rendered 1, figure_region_images_absorbed 283, figure_region_lines_suppressed 54,
figure_region_chars_suppressed 528` → INFO (сегодня — WARNING с `skipped 261`). US1 + US2 — `emitted 34`,
`figure_regions_rendered 33`, `figure_region_images_absorbed 315`. Money / Creating / Value — как сегодня, новые
счётчики нулевые.

## `pdf_text_layer_import_succeeded` — два новых ключа

`figure_regions_rendered`, `figure_region_lines_suppressed` (из `_PdfParseStagesResult`, data-model §6); `image_count`
— длина итогового списка.

## Документы

- `docs/LOGGING_AND_ARTIFACT_RETENTION.md`: события `pdf_image_extraction_*` уходят из §3.8 («зарегистрированы, не
  описаны») в описанные; три новых события — новым подразделом §3.15 «Спека 082: области иллюстраций PDF»; запись в §7.
- `scripts/_list_log_events.py`: `TARGETS` += `src/docxaicorrector/pdf_import/images.py`,
  `src/docxaicorrector/pdf_import/figure_render.py` (сегодня `images.py` там нет, и его события скрипт не видит).
