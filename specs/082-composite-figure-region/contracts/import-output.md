# Contract: что выдаёт импорт PDF после среза A спеки 082

**Spec**: [../spec.md](../spec.md) FR-A1…FR-A14 | **Date**: 2026-11-13 (раунд 2; поправки приёмочного ревью среза A)

## Спаны

Срез A спанов не трогает: `_run_pdf_parse_stages` (`processing_runtime.py:511-601`) возвращает тот же список, что
вернул `extract_pdf_text_spans_with_pdfminer` (или OCR-путь). Абзацы равны по построению.

## Список картинок

- Те же картинки, тот же порядок `(page_number, top, x0)` (`images.py:126`), те же `source_index`, рамки и
  `discovery_index`; заменена только картинка, антикоррелирующая с отрисовкой своей рамки (FR-A1) и не попавшая под
  отказ (FR-A2, FR-A4, FR-A7): `image_bytes` = PNG отрисовки рамки, `mime_type="image/png"`, явный размер `display_*` и
  исходные байты в `original_*`. В ветке OCR — ни одной замены (FR-A14).
- Раунд 2 приёмочного ревью: `top`/`bottom` картинки по-прежнему прижаты к странице (ключ порядка и `source_index` не
  меняются), а её истинная рамка — в новом поле `frame_box`; по нему идут проверки допуска. Раунд 3: новые поля
  `ink_space` (причина: пространство краски) и `mask` (`/SMask` или `/Mask` в словаре картинки) читаются при обходе,
  никогда не бросают и в DOCX не попадают; поля раунда 2 `clips` и `PdfImageExtraction.painted` удалены вместе с
  наблюдателем краски. Извлечение снова идёт через `pdfminer.high_level.extract_pages`, как до раунда 2.
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
- `scripts/docker-ci-parity.sh` ставит `.[dev]`, гоняет на нём pyright-ratchet (как задание `editable-install`
  в `ci.yml`), затем ставит `requirements.txt` (`:36-40`) и только после этого — статический ярус и основной набор
  (как задание `tests`). До спеки 082 `requirements.txt` здесь не ставился, и в контейнере паритета не было
  PDF-зависимостей; спека это исправила (приёмочное ревью среза A, находка 9; порядок проверяет
  `tests/test_script_contract_static.py`). Прежняя строка этого контракта «спека его не меняет» стала неверной
  после той правки (приёмочное ревью, раунд 2, находка 5).
- Системных пакетов не добавляется.
