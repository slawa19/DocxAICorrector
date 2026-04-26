# Changelog

## 2026-04-26

- Добавлен PDF как входной формат через upload normalization boundary: PDF конвертируется LibreOffice Writer import filter в canonical DOCX, после чего существующий DOCX pipeline продолжает работу без PDF-specific document model.
- Source token для PDF строится по original PDF bytes, чтобы cache/restart identity не зависела от nondeterministic DOCX output LibreOffice.
- UI upload flow теперь принимает `DOCX/DOC/PDF` и показывает best-effort предупреждение о PDF import.
- Добавлен setup contract для нового WSL/server runtime: `system-requirements.apt`, `scripts/setup-wsl.sh`, `scripts/setup-project.ps1`, VS Code task `Setup Project`, а `Project Status` проверяет LibreOffice availability.
- Подтверждена реальная PDF -> DOCX normalization на `tests/sources/Are_We_In_The_End_Times.pdf`; targeted WSL tests проходят для runtime, app preparation, application flow и setup workflow smoke.

## 2026-03-22

- Завершён и зафиксирован Phase 1 document-entity round-trip hardening: mainline DOCX output теперь опирается на dynamic reference DOCX baseline и минимальный post-Pandoc formatting pass вместо broad source-XML replay.
- Усилена extraction-semantics в `document.py`: heading heuristics теперь работают по normalized plain text, различают chapter/section cues и корректно учитывают inherited style alignment без роста ложных срабатываний.
- Исправлен корневой real-document list regression: paragraphs с реальным Word `numPr` теперь распознаются как ordered/unordered list entities даже без видимых `1.` markers в тексте.
- Расширено regression coverage для image assets, inherited heading detection, caption anchoring, compatibility no-op behavior и reference DOCX numbering/style baseline.
- Переписан ordered-list generation contract test: он теперь проверяет стабильную Word-numbering semantics после Pandoc instead of overfitting to one exact numbering-definition layout.
- Завершён user-visible full pytest verification path через VS Code task: `479 passed, 5 skipped`.

## 2026-03-21

- Реализована universal real-document validation architecture: registry-driven document profiles, независимые run profiles, deterministic `extraction`/`structural` tiers и profile-driven full validator.
- Добавлен repeat/soak orchestration для full-tier real-document validation с агрегированием intermittent failures и per-repeat acceptance outcome.
- Введён project-level legacy `.doc` normalization layer в `processing_runtime.py` с auto-detection по magic bytes и backends `soffice` или `antiword + pandoc`.
- Preparation, extraction, structural validation и full real-document validator переведены на единый путь normalizer -> DOCX bytes вместо DOCX-only contract.
- Второй corpus document `religion-wealth-core` переведён на исходный legacy `.doc`, чтобы multi-document architecture проверялась на реальном mixed corpus.
- Усилено regression coverage для `heading_only_output`: добавлены тесты на real-document failure-classification path и на legacy DOC normalization в runtime/application-flow/document path.
- Полный pytest suite в WSL проходит: `450 passed, 5 skipped`.

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
