# Contract: что выдаёт импорт PDF после среза A спеки 082

**Spec**: [../spec.md](../spec.md) FR-A1…FR-A13 | **Date**: 2026-11-13 (раунд 2)

## Спаны

Срез A спанов не трогает: `_run_pdf_parse_stages` (`processing_runtime.py:511-601`) возвращает тот же список, что
вернул `extract_pdf_text_spans_with_pdfminer` (или OCR-путь). Абзацы равны по построению.

## Список картинок

- Те же картинки, тот же порядок `(page_number, top, x0)` (`images.py:126`), те же `source_index`, рамки и
  `discovery_index`; у картинки-замены — `image_bytes` = PNG отрисовки рамки, `mime_type="image/png"`, явный размер
  `display_*` и исходные байты в `original_*`.
- `_enforce_pdf_image_count_cap` (`:619-631`) — как сегодня (число картинок не меняется).

## Картинка в DOCX

- Картинка без `display_*` — как сегодня: `add_picture` без размера (`:1101-1104`).
- Замена — `add_picture(width=Emu(round(display_width_points × 12700)), height=Emu(round(display_height_points × 12700)))`.
- Сбой вставки замены → исходные байты прежним путём (`_append_pdf_image_to_docx`, `:1057-1098`, с его коэрсией) +
  ERROR `pdf_image_replacement_insert_failed`.
- Альт-текста нет (как у всех картинок PDF сегодня); роль `image`, не озвучивается
  (`document/narration_exclusion.py:152-153`); режимы изображений — как для любой картинки.

## Неизменное

- Картинки вне триггера: байты (sha1), рамка, `source_index`, порядок.
- Токен загрузки — по исходным байтам PDF (`docs/WORKFLOW_AND_IMAGE_MODES.md:95`).

## Зависимость

- `requirements.txt`: `pypdfium2==5.15.2`; `pyproject.toml` `[project.optional-dependencies].pdf-import` — то же.
- `scripts/setup-wsl.sh` `verify_runtime` (`:65-72`): импорты += `pdfminer`, `pypdfium2`.
- `scripts/docker-ci-parity.sh` ставит `.[dev]` (без `pdf-import`), как и сегодня для `pdfminer` — расхождение с CI
  (`ci.yml` ставит `requirements.txt`) существовало до спеки; спека его не меняет.
- Системных пакетов не добавляется.
