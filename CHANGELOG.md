# Changelog

## 2026-03-13

- Усилена DOCX-semantic extraction: добавлены heading levels через style-name и `outlineLvl`, а также более консервативная классификация заголовков.
- Введён ordered block traversal по DOCX body, чтобы сохранять таблицы в порядке документа вместо paragraph-only extraction.
- Добавлена поддержка таблиц как отдельных semantic blocks с передачей в Pandoc через HTML table markup.
- Добавлена семантика caption для подписей к изображениям и таблицам.
- Расширено сохранение inline-semantics: hyperlinks, tabs, bold, italic, underline, superscript и subscript.
- Добавлен controlled Pandoc `reference-doc` для более чистого и консистентного итогового DOCX.
- Добавлен отдельный semantic post-normalization pass для headings, body, captions, lists, tables и image paragraphs.
- Протянуты `source_paragraphs` и semantic DOCX normalization через background runtime, processing service и document pipeline.
- Добавлена отдельная спецификация hardening-а форматирования DOCX в `docs/DOCX_FORMATTING_HARDENING_SPEC_2026-03-13.md`.
- Полный pytest suite в WSL проходит: `244 passed, 4 skipped`.

## 2026-03-12

- Переведено хранение `completed_source` на metadata-only с payload в `.run/`.
- Добавлены startup-cleanup persisted-source файлов и ранняя проверка размера DOCX upload.
- Синглтон `ProcessingService` сделан thread-safe.
- Дедуплицирована логика подготовки документа и centralized progress helper.
- Введён типизированный `AppConfig` с совместимостью по `Mapping`-контракту.
- Добавлены `ImageMode` и общие image-mode constants.
- Логгер переведён на lazy initialization без side effect при import.
- Убран дубликат retryable error helper, улучшено клонирование preparation cache без лишнего копирования image bytes.
- Добавлено покрытие для `document_pipeline.py`, `app_runtime.py`, `logger.py` и Pandoc integration seam в `generation.py`.