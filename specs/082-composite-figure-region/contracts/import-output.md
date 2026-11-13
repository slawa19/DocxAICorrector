# Contract: что выдаёт импорт PDF после спеки 082

**Spec**: [../spec.md](../spec.md) FR-006…FR-011, FR-014 | **Date**: 2026-11-13

## Спаны, идущие в сборку абзацев

`_run_pdf_parse_stages` (`processing_runtime.py:511-601`) возвращает `spans` БЕЗ строк, убранных принятыми областями
(FR-006). Отчёт качества текстового слоя (`:550`) считается на полном списке ДО правила — решение
`promising`/нет и `body_text_ratio` не меняются. `build_paragraph_units_from_text_spans` (`:887`) получает уже
отфильтрованный список; его профиль считается на нём (замер: на корпусе вне стр. 151 абзацы те же — research R11).

## Список картинок

- Отдельные картинки — как сегодня (`images.py:84-98`), кроме поглощённых областями.
- Картинки областей — по одной на область (data-model §4).
- Порядок — `(page_number, top, x0)` (`images.py:126`); слияние с абзацами — прежнее
  (`processing_runtime.py:896-912`: ключ `source_index`, картинка раньше абзаца при равенстве).
- `_enforce_pdf_image_count_cap` (`:619-631`) — к итоговому списку.

## Картинка в DOCX

- `_append_image_bytes_to_docx` (`:1101-1109`) вставляет без явной ширины — размер берётся из `pHYs` PNG области, и он
  равен рамке области (SC-006; research R10).
- Если у `PdfImageObject` есть `description`, он записывается в `wp:inline/wp:docPr/@descr` вставленной картинки.
  Дальше его переносит существующий путь: разбор DOCX (`document/shared_xml.py:229-240`) → выходной DOCX
  (`image/reinsertion.py:830-850`). Перевод, озвучка, модели его не читают.
- Картинка области — абзац с ролью `image`, не озвучивается (`document/narration_exclusion.py:152-153`).

## Неизменное

- Страница без семени: спаны и картинки — побайтно как до спеки (Anti-regression 1).
- Отдаваемые картинки вне областей: байты, рамка, `source_index` (Anti-regression 5).
- Ключи и поля `PdfTextSpan`; роли и стили импортёра; формат DOCX моста (`mark_document_as_pdf_bridge_output`, `:895`).
- Токен загрузки (`build_uploaded_file_token`) — по исходным байтам PDF (`docs/WORKFLOW_AND_IMAGE_MODES.md:95`); кэш
  подготовки старой книги пересчитается только при новой загрузке.

## Зависимость

- `requirements.txt`: `pypdfium2==5.15.2`; `pyproject.toml` `[project.optional-dependencies].pdf-import` — то же.
- `scripts/setup-wsl.sh` `verify_runtime` (`:65-72`): кортеж импортов += `pdfminer`, `pypdfium2`.
- Системных пакетов не добавляется; `system-requirements.apt` и CI не меняются.
