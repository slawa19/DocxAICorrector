# Changelog

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