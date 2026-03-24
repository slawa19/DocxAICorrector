# Расширенный код-ревью проекта DocxAICorrector

> Статус: archived point-in-time review snapshot на 2026-03-12. Этот документ фиксирует состояние проекта на дату ревью и не заменяет `README.md` и `docs/WORKFLOW_AND_IMAGE_MODES.md` как источники текущих контрактов.

**Дата:** 12 марта 2026  
**Ревизия:** все модули (`*.py`, `tests/`, `prompts/`, конфигурация)  
**Общий объём кода:** ~7 500 строк продакшен-кода, ~3 000 строк тестов (204 тест-функции)

---

## 1. Общая оценка

Проект представляет собой зрелый AI-инструмент для редактирования DOCX-документов через Markdown-представление с многоуровневой обработкой изображений. Архитектура чистая, модули хорошо декомпозированы, зоны ответственности разделены. Ниже — детальные замечания, ранжированные по критичности.

### Статус исправлений на 12 марта 2026

- Исправлено (проверено повторно): все 31 из первоначального ревью — `2.1`–`2.4`, `3.1`–`3.7`, `4.1`–`4.5`, `5.1`–`5.6`, `6.1`–`6.3`, `7.1`–`7.3`, `8.1`–`8.3`, `9.1`–`9.2`
- Исправлено дополнительно: все 9 новых замечаний повторной верификации — `11.1`–`11.9`
- Исправлено: все 4 замечания третьей верификации — `12.1`–`12.4`

---

## 2. Критические замечания (P0)

### 2.1. Хранение `source_bytes` в `session_state.completed_source` — утечка памяти

**Статус:** Исправлено 12.03.2026 — `completed_source` переведён на metadata-only хранение с payload в `.run/` через `restart_store`.

**Файл:** `processing_runtime.py` (drain_processing_events → WorkerCompleteEvent)  
**Проблема:** При outcome == SUCCEEDED полный байтовый массив DOCX (до 8 МБ, MAX_COMPLETED_SOURCE_BYTES) сохраняется в `session_state.completed_source["source_bytes"]`. Streamlit session state хранится в памяти сервера. При нескольких параллельных пользовательских сессиях и многократных загрузках это приводит к линейному росту потребления памяти без механизма eviction.

**Рекомендация:** Использовать `restart_store` (файловое хранилище в `.run/`) аналогично restart-flow вместо хранения source_bytes in-memory. Либо ввести TTL/LRU для completed_source в session_state.

---

### 2.2. Отсутствие ограничения размера загружаемого файла на уровне Streamlit

**Статус:** Исправлено 12.03.2026 — добавлены `.streamlit/config.toml` с `server.maxUploadSize = 25` и ранняя проверка `uploaded_file.size` в `app.py`.

**Файл:** `app.py` (st.file_uploader)  
**Проблема:** `st.file_uploader` не задаёт параметр `max_upload_size`. Ограничение `MAX_DOCX_ARCHIVE_SIZE_BYTES = 25 MB` проверяется только после полного чтения и распаковки в `document.py._validate_docx_archive`. К этому моменту файл уже занимает память.

**Рекомендация:** Добавить `max_upload_size_mb` в Streamlit конфигурацию (`.streamlit/config.toml`) или задать через `server.maxUploadSize`. Дополнительно — валидировать размер до вызова `extract_document_content_from_docx`.

---

### 2.3. Глобальный синглтон `_DEFAULT_PROCESSING_SERVICE` не thread-safe

**Статус:** Исправлено 12.03.2026 — доступ к singleton обёрнут в `threading.Lock`.

**Файл:** `processing_service.py`  
**Проблема:** `get_processing_service()` и `reset_processing_service()` оперируют модуль-уровневой переменной `_DEFAULT_PROCESSING_SERVICE` без какой-либо синхронизации. При нескольких Streamlit-сессиях на одном сервере (shared process) возможен data race, в т.ч. двойная инициализация.

**Рекомендация:** Обернуть в `threading.Lock()` или использовать `functools.cache` с thread-safe гарантией.

---

### 2.4. Race condition в shared preparation cache

**Статус:** Исправлено 12.03.2026 — инвариант thread-ownership `session_state` зафиксирован комментарием в cache-path; background worker по-прежнему работает только с `session_state=None`.

**Файл:** `preparation.py`  
**Проблема:** `_shared_preparation_cache` — модуль-уровневой `OrderedDict` с `Lock`. Однако `_read_cached_prepared_document` сначала проверяет session cache без блокировки, потом обращается к shared cache с блокировкой, и после этого мутирует session cache снова без блокировки. В Streamlit каждый rerun по собственной thread'е, и session_state может быть мутирован из preparation worker одновременно.

**Рекомендация:** Документировать thread-ownership session_state (Streamlit гарантирует per-rerun single-thread, но worker thread'ы работают параллельно). При background_preparation `session_state=None`, поэтому race маловероятен — но стоит явно зафиксировать этот инвариант через комментарий или assert.

---

## 3. Важные замечания (P1)

### 3.1. Двойная реализация `_emit_preparation_progress`

**Статус:** Исправлено 12.03.2026 — helper оставлен в `preparation.py` и переиспользуется из orchestration-слоя.

**Файлы:** `preparation.py` и `application_flow.py`  
**Проблема:** Функция `_emit_preparation_progress` скопирована с идентичной сигнатурой и реализацией в оба модуля. Нарушение DRY.

**Рекомендация:** Вынести в общий модуль (`processing_runtime.py` или новый `progress.py`) или оставить только в `preparation.py` и импортировать.

---

### 3.2. Дублирование `prepare_run_context` и `prepare_run_context_for_background`

**Статус:** Исправлено 12.03.2026 — общая подготовительная логика вынесена в приватный core-helper с разделением foreground/background-специфики.

**Файл:** `application_flow.py`  
**Проблема:** Обе функции содержат ~80% одинакового кода: чтение файла → построение токена → вызов `prepare_document_for_processing` → валидация → построение `PreparedRunContext`. Разница: в foreground-версии есть `sync_selected_file_context`, логирование через `log_event_fn`, вызов `fail_critical_fn`, обращение к `session_state`. Background-версия упрощена.

**Рекомендация:** Извлечь общую core-логику в приватную функцию, передавая опциональные callback-и для session-зависимых действий.

---

### 3.3. Конфигурация как нетипизированный `dict[str, object]`

**Статус:** Исправлено 12.03.2026 — введён типизированный `AppConfig` с совместимым `Mapping`-контрактом для существующего кода.

**Файл:** `config.py`  
**Проблема:** `load_app_config()` возвращает `dict[str, object]` с ~30 ключами. По всему проекту конфигурационные значения извлекаются через `config.get("key", default)` с ручным приведением типов (`int(...)`, `float(...)`, `bool(...)`). Это приводит к:
- Разбросу magic strings по всему коду
- Риску рассинхронизации default-значений между модулями
- Отсутствию IDE-подсказок и тайп-чекинга

**Рекомендация:** Ввести `@dataclass AppConfig` с типизированными полями и единой точкой валидации. Заменить `dict` на `AppConfig` по всему проекту.

---

### 3.4. Монолитная функция `process_document_images` с 20+ параметрами

**Статус:** Исправлено 12.03.2026 — введён `ImageProcessingContext`, публичный `ProcessingService.process_document_images(...)` сохранён, внутренний pipeline переведён на единый context-object.

**Файл:** `image_pipeline.py`  
**Проблема:** Функция `process_document_images` принимает 22 именованных параметра, включая 12 callable-зависимостей. Это затрудняет понимание, тестирование, и делает сигнатуру нечитаемой.

**Рекомендация:** Создать `ImageProcessingContext` dataclass, который инкапсулирует callback-зависимости (`emit_state`, `emit_activity`, `analyze_image_fn` и т.д.), и передавать единым объектом. Альтернативно — декомпозировать на стратеги-объект с методами.

---

### 3.5. Отсутствие тестового покрытия для `document_pipeline.py`

**Статус:** Исправлено 12.03.2026 — добавлен `tests/test_document_pipeline.py` с happy path, stop, empty block и mismatch-сценариями.

**Файл:** `document_pipeline.py` (376 строк)  
**Проблема:** Это ключевой orchestration-модуль, проводящий блок-за-блоком обработку через LLM + image pipeline + DOCX-сборку. При этом тестов для него нет вообще. Coverage gap критичен, потому что:
- Все error-path-и (пустой блок, mismatch counts, placeholder integrity) не проверены
- Stop-механизм не покрыт
- Логирование не проверяется

**Рекомендация:** Создать `tests/test_document_pipeline.py` с мок-сценариями: happy path, stop-at-block-2, empty-processed-block, block-count-mismatch.

---

### 3.6. `app_runtime.py` — пустой тестовый coverage

**Статус:** Исправлено 12.03.2026 — добавлены smoke-тесты на делегирование wrapper-функций в `tests/test_app_runtime.py`.

**Файл:** `app_runtime.py` (68 строк)  
**Проблема:** Модуль — связующий слой, но содержит логику по сборке параметров для `start_background_processing_impl` и `start_background_preparation_impl`. Ошибка в маршрутизации параметров не будет обнаружена до ручного тестирования.

**Рекомендация:** Добавить хотя бы smoke-тесты, проверяющие, что вызовы транслируются корректно.

---

### 3.7. Опечатка в коде: корейский текст в ошибке

**Статус:** Исправлено 12.03.2026 — строка активности нормализована на `Блок`.

**Файл:** `document_pipeline.py`, строка ~144  
**Проблема:** `emit_activity(runtime, f"블ок {index}: ошибка обработки.")` — слово "블ок" написано на корейском вместо "Блок". Это копипаст-ошибка.

**Рекомендация:** Заменить на `Блок`.

---

## 4. Архитектурные замечания (P2)

### 4.1. Сверхглубокая передача зависимостей (dependency threading)

**Статус:** Исправлено 12.03.2026 — callback/emit/dependency wiring для image pipeline свернуты в `ImageProcessingContext`; `processing_service.py` теперь собирает контекст на границе слоя.

**Файлы:** `processing_service.py`, `document_pipeline.py`, `image_pipeline.py`  
**Паттерн:** Зависимости от `analyze_image`, `generate_image_candidate`, `validate_redraw_result` и десятков emit-функций передаются через 3-4 уровня вложенности: `ProcessingService → run_document_processing → process_document_images → select_best_semantic_asset`.

**Проблема:** Каждый новый callback требует пробрасывания через все промежуточные уровни. Это создаёт maintenance burden и делает рефакторинг дорогим.

**Рекомендация:** Рассмотреть контейнер зависимостей (простой `@dataclass ImagePipelineContext`) или Protocol-based strategy-класс для group-инъекции.

---

### 4.2. `_call_with_supported_kwargs` как anti-pattern

**Статус:** Исправлено 12.03.2026 — runtime reflection удалён; `analyze_image`, `generate_image_candidate`, `validate_redraw_result` используют явные согласованные сигнатуры, а тестовые seams обновлены под них.

**Файл:** `image_pipeline.py`  
**Проблема:** Функция `_call_with_supported_kwargs` использует `inspect.signature()` в runtime, чтобы фильтровать kwargs перед вызовом. Это неявное связывание: caller не знает, какие параметры будут выброшены, а callee не знает, какие параметры ему не дойдут. Это:
- Маскирует ошибки рассинхронизации сигнатур
- Замедляет вызовы (runtime reflection на каждый image)
- Нарушает fail-fast принцип

**Рекомендация:** Явно определить интерфейсы (Protocol / ABC) для `analyze_image_fn`, `generate_image_candidate_fn`, `validate_redraw_result_fn`. Убрать `_call_with_supported_kwargs`. Если backward compatibility важна — зафиксировать единые сигнатуры и адаптировать реализации.

---

### 4.3. Отсутствие `pyproject.toml` / `pytest.ini`

**Статус:** Исправлено 12.03.2026 — добавлен `pyproject.toml` с `pytest`-настройками и `tests/conftest.py`.

**Проблема:** Нет конфигурации тестового раннера. `pytest` всё находит по конвенции, но:
- Нет настроек `testpaths`, `filterwarnings`, `markers`
- Нет `conftest.py` с общими fixture'ами
- Нет CI-конфигурации

**Рекомендация:** Создать `pyproject.toml` с секцией `[tool.pytest.ini_options]`, задать `testpaths = ["tests"]`, добавить `conftest.py` с общими fixture'ами (fake_image_bytes, mock_client, app_config).

---

### 4.4. Глобальная инициализация логгера при импорте модуля

**Статус:** Исправлено 12.03.2026 — логгер переведён на lazy initialization через `get_logger()`.

**Файл:** `logger.py`  
**Проблема:** `LOGGER = setup_logger()` вызывается при первом `import logger`. Это создаёт директорию `.run/` как side effect импорта, что может мешать тестированию и развертыванию.

**Рекомендация:** Ленивая инициализация: `_LOGGER: Logger | None = None; def _get_logger() -> Logger: ...`. Либо зарегистрировать setup в entrypoint (`app.py`).

---

### 4.5. `models.py`: bytes-поля в dataclass'ах

**Статус:** Исправлено 12.03.2026 — preparation cache перестал делать полный `deepcopy` image-bytes; для image-assets используется более дешёвое selective cloning.

**Файл:** `models.py`  
**Проблема:** `ImageAsset` и `ImageVariantCandidate` содержат поля `original_bytes`, `safe_bytes`, `redrawn_bytes`, `bytes`. При `deepcopy` (используется в `_clone_prepared_document`, `_clone_image_asset_for_attempt`) эти байтовые массивы копируются целиком. Для изображений ~2-5 МБ на каждое — это существенный расход памяти, особенно при multi-attempt semantic redraw (до 3 попыток × 3 варианта в compare_all).

**Рекомендация:** Хранить image bytes в content-addressable store (dict по hash), а в dataclass держать только ключ/ссылку. Либо заменить `deepcopy` на shallow-copy с copy-on-write семантикой для bytes-полей (bytes immutable, их можно безопасно не копировать).

---

## 5. Замечания по стилю и качеству кода (P3)

### 5.1. Непоследовательное использование типов для параметров

**Статус:** Исправлено 12.03.2026 — добавлены `Protocol`-аннотации для `session_state` и uploaded-file seam.

**Файл:** `application_flow.py`  
**Проблема:** Многие функции принимают `session_state` с типом `object` без аннотации. Фактически это Streamlit `SessionStateProxy`, но параметры аннотированы молча. Аналогично `uploaded_file` — это `UploadedFile | BytesIO`, но нигде не аннотирован.

**Рекомендация:** Ввести `typing.Protocol` или `TypeAlias` для `SessionState` и `UploadedFile`, хотя бы для документирования.

---

### 5.2. Magic numbers в heuristic analysis

**Статус:** Исправлено 12.03.2026 — ключевые heuristic thresholds вынесены в именованные константы с поясняющим комментарием.

**Файл:** `image_analysis.py`  
**Проблема:** Пороговые значения для классификации изображений (`white_ratio >= 0.55`, `edge_ratio >= 0.06`, `bright_ratio >= 0.82`, `colorful_ratio >= 0.12`) — сотни magic numbers без объяснения их происхождения.

**Рекомендация:** Вынести в именованные константы с docstring, объясняющим источник (эмпирика, A/B-тест, бенчмарк). Хотя бы верхнеуровневый комментарий.

---

### 5.3. Неиспользуемый импорт `time` в `state.py`

**Статус:** Исправлено 12.03.2026 — добавлены явные helper'ы `_current_unix_timestamp()` и `_current_clock_label()`, что закрепило разделение machine timestamps и display-time форматирования.

**Файл:** `state.py`, строка 1  
**Проблема:** `import time` используется, но `from datetime import datetime` тоже импортирован. В `push_activity` используется `datetime`, в `set_processing_status` — `time.time()`. Непоследовательно.

**Рекомендация:** Унифицировать: использовать `time.time()` для timestamps и `datetime.now().strftime()` для форматирования, как сейчас. Замечание минорное.

---

### 5.4. Жёсткие строковые ключи вместо Enum для `image_mode`

**Статус:** Исправлено 12.03.2026 — введён `ImageMode(StrEnum)` и центральные mode-константы, подключённые в конфиге и UI/policy-слое.

**Файлы:** `app.py`, `image_pipeline.py`, `image_generation.py`, `ui.py`  
**Проблема:** Значения `"safe"`, `"semantic_redraw_direct"`, `"semantic_redraw_structured"`, `"compare_all"` — строковые литералы, разбросанные по 10+ файлам. Опечатка в любом из них не поймается до runtime.

**Рекомендация:** Создать `ImageMode(StrEnum)` в `models.py` или `workflow_state.py` и использовать повсюду.

---

### 5.5. Дублирование `_read_uploaded_docx_bytes` и `read_uploaded_file_bytes`

**Статус:** Исправлено 12.03.2026 — чтение DOCX теперь переиспользует общий helper `read_uploaded_file_bytes`.

**Файлы:** `document.py` и `processing_runtime.py`  
**Проблема:** Обе функции идентичны по логике: `seek(0)` → `getvalue()/read()` → проверка типа → возврат `bytes`. Различие: одна обрабатывает DOCX, другая — любой uploaded file. Но реализация одинакова.

**Рекомендация:** Объединить в единую utility-функцию.

---

### 5.6. `is_retryable_error` дублируется между модулями

**Статус:** Исправлено 12.03.2026 — retryable error helper вынесен в `image_shared.py`; вызовы синхронизированы.

**Файлы:** `generation.py` и `image_generation.py`  
**Проблема:** `generation.py` определяет `is_retryable_error`. `image_generation.py` определяет `_is_retryable_api_error` с почти идентичной логикой. `image_analysis.py` и `image_validation.py` импортируют из `generation.py`.

**Рекомендация:** Выделить единую `is_retryable_error` в `image_shared.py` (который уже содержит `call_responses_create_with_retry`).

---

## 6. Замечания по безопасности (P1)

### 6.1. Отсутствие rate-limiting для API-вызовов OpenAI

**Статус:** Исправлено 12.03.2026 — добавлен document-level `image_model_call_budget_per_document`, budget протянут через analysis/generation/validation и учитывается на каждом `responses.create` retry.

**Файлы:** `generation.py`, `image_generation.py`, `image_analysis.py`, `image_validation.py`, `image_reconstruction.py`  
**Проблема:** В compare_all-режиме для одного документа с 10 изображениями может быть выполнено до ~60-90 API-вызовов (3 варианта × analysis + generation + validation × retry). Нет глобального rate-limiter'а или budget tracker'а на уровне сессии.

**Рекомендация:** Реализовать session-level budget (аналогично `ImageModelCallBudget`, но шире — на всю обработку документа), чтобы предотвратить аномально высокий cost runaway.

---

### 6.2. `restart_store` файлы в `.run/` не ограничены по количеству

**Статус:** Исправлено 12.03.2026 — добавлен startup-cleanup устаревших `restart_*` и `completed_*` файлов.

**Файл:** `restart_store.py`  
**Проблема:** `store_restart_source` очищает предыдущий restart source, но при crash/unclean shutdown старые файлы могут накапливаться. Нет периодической очистки `RUN_DIR` от orphaned файлов.

**Рекомендация:** Добавить startup-cleanup в `app.py`: при запуске удалять файлы `restart_*` старше N часов.

---

### 6.3. Открытый `unsafe_allow_html=True` в UI

**Статус:** Исправлено 12.03.2026 — HTML-рендеринг сведён к helper-обёртке с явным комментарием про trusted markup и escape-contract.

**Файл:** `ui.py`  
**Проблема:** Множественные вызовы `st.markdown(..., unsafe_allow_html=True)`. Данные из `processing_status`, `activity_feed` и `run_log` подставляются в HTML. Все пользовательские строки обёрнуты в `html.escape()` — это хорошо. Однако если в будущем добавится отображение данных из LLM-ответов без экранирования, возникнет XSS-уязвимость.

**Рекомендация:** Добавить review-маркер (комментарий) ко всем `unsafe_allow_html=True`, указывающий источник данных и что escape гарантирован. Рассмотреть helper-обёртку.

---

## 7. Замечания по производительности (P2)

### 7.1. Pixel-by-pixel обработка в `_extract_visual_features`

**Статус:** Исправлено 12.03.2026 — nested `getpixel()` loops заменены на линейный проход по contiguous byte buffer и быстрый edge scan без coordinate lookups.

**Файл:** `image_analysis.py`  
**Проблема:** Циклы `for y in range(height): for x in range(width): preview.getpixel(...)` — крайне медленный способ анализа пикселей в Python. Для preview 256×256 = 65 536 вызовов `getpixel`. Для edge_map — ещё столько же.

**Рекомендация:** Заменить на numpy-based анализ:
```python
import numpy as np
arr = np.array(preview)
white_mask = (arr.min(axis=2) >= 235) & (arr.max(axis=2) >= 245)
white_ratio = white_mask.sum() / pixel_count
```

---

### 7.2. `load_image_prompt_registry()` вызывается без кэширования

**Статус:** Исправлено 12.03.2026 — registry кэшируется через `functools.lru_cache(maxsize=1)`.

**Файл:** `image_prompts.py`  
**Проблема:** Каждый вызов `get_image_prompt_profile` → `load_image_prompt_registry` читает и парсит TOML с диска. При обработке документа с 10 изображениями и 3 вариантами — до 30 чтений одного и того же файла.

**Рекомендация:** Добавить `@functools.lru_cache` или module-level кэш.

---

### 7.3. `deepcopy` образов в preparation cache

**Статус:** Исправлено 12.03.2026 — cloning preparation cache стал selective и больше не копирует image bytes целиком без необходимости.

**Файл:** `preparation.py`  
**Проблема:** `_clone_prepared_document` делает `deepcopy(data.paragraphs)`, `deepcopy(data.image_assets)`, `deepcopy(data.jobs)`. Для документов с изображениями `deepcopy(image_assets)` клонирует все `original_bytes` каждого изображения — это может быть десятки мегабайт.

**Рекомендация:** `bytes` — immutable, deepcopy не нужен для них. Реализовать shallow-copy с явным пересозданием mutable полей, оставляя bytes-ссылки общими.

---

## 8. Замечания по тестированию (P2)

### 8.1. Отсутствие `conftest.py` с общими fixture'ами

**Статус:** Исправлено 12.03.2026 — добавлен `tests/conftest.py` с общими fixtures.

**Проблема:** Каждый тестовый файл самостоятельно создаёт mock-объекты для `ImageAsset`, `ImageAnalysisResult`, `client`, `config`. Много дублирования.

**Рекомендация:** Создать `tests/conftest.py` с fixture'ами: `fake_png_bytes`, `make_analysis_result(...)`, `make_image_asset(...)`, `mock_openai_client(...)`.

---

### 8.2. Нет тестов на `logger.py`

**Статус:** Исправлено 12.03.2026 — добавлен `tests/test_logger.py`.

**Файл:** `logger.py` (161 строка)  
**Проблема:** Модуль содержит нетривиальную логику: `extract_exception_message`, `format_user_error` (маршрутизация по status_code), `sanitize_log_context` (рекурсивная обработка). Ни одна из этих функций не покрыта тестами.

**Рекомендация:** Добавить `tests/test_logger.py` с тестами на каждую ветку `format_user_error` и edge-case'ы `sanitize_log_context`.

---

### 8.3. Тесты `generation.py` не покрывают Pandoc-интеграцию

**Статус:** Исправлено 12.03.2026 — добавлен unit-test на Pandoc integration seam в `convert_markdown_to_docx_bytes`.

**Файл:** `tests/test_generation.py`  
**Проблема:** Тесты покрывают `normalize_model_output` , `is_retryable_error`, `build_output_filename`, но не `convert_markdown_to_docx_bytes` и не `generate_markdown_block`. Pandoc-зависимость не мокается и не тестируется.

**Рекомендация:** Добавить интеграционный тест с мок-pandoc или пометить `@pytest.mark.integration` тесты, требующие установленного pandoc.

---

## 9. Замечания по документации (P3)

### 9.1. README.md не описывает настройку `.env`

**Статус:** Исправлено 12.03.2026 — README дополнен описанием supported `.env` variables и примером полного файла.

**Проблема:** Приложение требует `OPENAI_API_KEY` в `.env`, но README не документирует формат `.env`-файла, обязательные переменные окружения и их описание.

---

### 9.2. Отсутствие CHANGELOG

**Статус:** Исправлено 12.03.2026 — добавлен `CHANGELOG.md`.

**Проблема:** При наличии нескольких CODE_REVIEW_REPORT и спецификаций нет единого лога изменений. Трудно отследить, какие рекомендации из прошлых ревью были реализованы.

---

## 10. Сводная таблица замечаний

*Перенесена в раздел 12 «Обновлённая сводная таблица замечаний».*

---

## 11. Новые замечания (выявлены при повторной верификации)

### 11.1. P1 — Дублирующий рендер текста в `_render_styled_matrix_table` (stale variable)

**Статус:** Исправлено 12.03.2026 — удалён stale-блок после inner loop; добавлен regression-test на single render per cell.

**Файл:** `image_reconstruction.py`, `_render_styled_matrix_table`  
**Категория:** Логика

После внутреннего цикла `for col_index in range(cols):` остался блок кода на уровне внешнего цикла `for row_index`, который повторно рендерит текст из **последней ячейки** каждой строки с **другим font_size** (0.5×height вместо 0.24/0.2×height). Переменная `cell` «утекает» из завершённого внутреннего цикла.

```python
        for col_index in range(cols):
            cell = cells_by_position.get(...)
            ...
            _draw_box_text(...)   # ← Первый рендер (корректный)

        # ↓ Выполняется ПОСЛЕ внутреннего цикла — stale `cell` из последней итерации
        text = cell.get("text", "")
        if text:
            font_size = ... int(ch * 0.5) ...
            _draw_box_text(...)   # ← ДУБЛИРУЮЩИЙ рендер с другим размером шрифта
```

Результат: **наложение текста** на последнюю ячейку каждой строки таблицы с несогласованным размером шрифта.

**Рекомендация:** Удалить весь блок после внутреннего `for col_index` цикла (от `text = cell.get("text", "")` до второго вызова `_draw_box_text`). Это остаточный код от предыдущей версии без styled rendering внутри inner loop.

---

### 11.2. P1 — Plain-table path не рендерит текст ячеек

**Статус:** Исправлено 12.03.2026 — plain-table path теперь рендерит текст ячеек; добавлен regression-test для non-styled branch.

**Файл:** `image_reconstruction.py`, блок рендеринга plain table (когда `_should_render_styled_matrix` → `False`)  
**Категория:** Логика

При отключённом styled-matrix (таблицы с <3 строк, >4 колонок, или <160px) plain path рисует сетку и заливку ячеек, но **не рендерит текст**:

```python
    for cell in cells:
        cr, cc = ...
        cell_fill = cell.get("fill")
        if cell_fill:
            draw.rectangle(...)
        # ← Нет рендеринга текста
```

Таблицы, не попадающие под styled-matrix criteria, получают пустые ячейки на выходе.

**Рекомендация:** Добавить рендеринг текста после блока заливки, аналогично styled path — используя `_draw_box_text` с `cell["text"]`, `font_size`, `font_color`.

---

### 11.3. P2 — Silent exception swallowing в vision validation

**Статус:** Исправлено 12.03.2026 — fallback на heuristic-only validation теперь сопровождается warning-log с типом и текстом исключения.

**Файл:** `image_validation.py`, `_maybe_build_vision_validation_assessment`  
**Категория:** Error Handling / Observability

```python
    try:
        return _build_vision_validation_assessment(...)
    except Exception:
        return None    # ← Полностью молча
```

API-ошибки, malformed responses, budget exhaustion и даже programming bugs в assessment-логике молча проглатываются. Caller получает `None` и переключается на heuristic-only validation без индикации, что vision validation была попытана и провалилась.

**Рекомендация:** Добавить `log_event(logging.WARNING, ...)` в except-блок с как минимум `exc.__class__.__name__` и `str(exc)`, аналогично тому, как `_generate_reconstructed_candidate` обрабатывает fallback logging.

---

### 11.4. P2 — O(W×H) Python pixel loop в `_normalize_generated_document_background`

**Статус:** Исправлено 12.03.2026 — маскированная замена фона переведена на `Image.composite(...)` без Python-level pixel loop.

**Файл:** `image_generation.py`, `_normalize_generated_document_background`  
**Категория:** Производительность

```python
    pixels = normalized.load()
    mask_pixels = border_mask.load()
    for y_coord in range(normalized.height):
        for x_coord in range(normalized.width):
            if mask_pixels[x_coord, y_coord]:
                pixels[x_coord, y_coord] = (255, 255, 255, 255)
```

Для изображения 2048×2048 — ~4M итераций на Python. Запускается на каждом semantic redraw candidate с тёмным фоном.

**Рекомендация:** Заменить на `Image.composite(white_canvas, normalized, border_mask)` — PIL выполнит ту же маскированную замену на C-уровне.

---

### 11.5. P2 — `getpixel()` loops в `_sample_source_background`

**Статус:** Исправлено 12.03.2026 — sampling border strips переведён на crop+tobytes scan без тысяч `getpixel()` вызовов.

**Файл:** `image_reconstruction.py`, `_sample_source_background`  
**Категория:** Производительность

```python
    for x_coord in range(width):
        for y_coord in range(sample):
            pixels.append(rgb_image.getpixel((x_coord, y_coord)))
            pixels.append(rgb_image.getpixel((x_coord, height - 1 - y_coord)))
```

Для 4000px-wide изображения с `sample=8` — ~96 000 вызовов `getpixel()`.

**Рекомендация:** Использовать array slicing через `np.array(rgb_image)` или PIL `.crop().getdata()`.

---

### 11.6. P2 — Глобальный `ImageFile.LOAD_TRUNCATED_IMAGES = True`

**Статус:** Исправлено 12.03.2026 — process-global override удалён; analysis снова использует дефолтное поведение PIL без глобального side effect.

**Файл:** `image_analysis.py`, строка 11  
**Категория:** Robustness

Это process-global side effect, позволяющий PIL молча загружать truncated или corrupt изображения **везде** в приложении, а не только в analysis. Corrupt image data может пропагировать через весь pipeline.

**Рекомендация:** Вместо глобальной настройки использовать context manager или try/except с explicit handling при загрузке изображений в `_extract_visual_features`, оставив глобальную настройку в default (`False`).

---

### 11.7. P2 — Implicit `get_client()` fallback нарушает DI-контракт

**Статус:** Исправлено 12.03.2026 — `extract_scene_graph` теперь требует explicit client и не обходит pipeline DI-контракт.

**Файл:** `image_reconstruction.py`, `extract_scene_graph`  
**Категория:** Дизайн / API

```python
    resolved_client = client or get_client()
```

Все остальные модули (`image_generation.py`, `image_validation.py`) **требуют** explicit client. Reconstruction молча fallback'ится к глобальному клиенту, что может обойти explicit client management в pipeline.

**Рекомендация:** Либо поднимать `RuntimeError` при отсутствии client, либо задокументировать и верифицировать этот fallback.

---

### 11.8. P3 — Exception chain потеряна в `_read_uploaded_docx_bytes`

**Статус:** Исправлено 12.03.2026 — `ValueError` теперь пробрасывается с `from exc`; добавлен test на сохранение `__cause__`.

**Файл:** `document.py`, `_read_uploaded_docx_bytes`  
**Категория:** Error Handling

```python
    except ValueError as exc:
        raise ValueError("Не удалось прочитать содержимое DOCX-файла.")  # ← нет `from exc`
```

Оригинальный traceback и сообщение теряются.

**Рекомендация:** Изменить на `raise ValueError("...") from exc`.

---

### 11.9. P3 — `ImageVariantCandidate.to_dict()` сериализует raw bytes

**Статус:** Исправлено 12.03.2026 — `to_dict()` стал JSON-safe: raw bytes исключены, вместо них возвращается summary (`has_bytes`, `bytes_size`).

**Файл:** `models.py`, `ImageVariantCandidate.to_dict()`  
**Категория:** Robustness

```python
    def to_dict(self) -> dict[str, object]:
        return {
            "mode": self.mode,
            "bytes": self.bytes,   # ← raw bytes, not JSON-serializable
            ...
        }
```

Попытка JSON-сериализации этого dict (например, для логирования) вызовет `TypeError`.

**Рекомендация:** Исключить `bytes` из dict, заменить на length/hash summary, или документировать что `to_dict()` не JSON-safe.

---

## 12. Обновлённая сводная таблица замечаний

### Исправленные замечания (все 31 из первоначального ревью):

| # | Приоритет | Категория | Краткое описание |
|---|-----------|-----------|-----------------|
| 2.1 | P0 | Память | Исправлено 12.03.2026 — payload `completed_source` вынесен из session_state в `.run/` |
| 2.2 | P0 | Безопасность | Исправлено 12.03.2026 — добавлены Streamlit upload limit и ранний size-guard |
| 2.3 | P0 | Concurrency | Исправлено 12.03.2026 — singleton `ProcessingService` защищён `Lock` |
| 2.4 | P0 | Concurrency | Исправлено 12.03.2026 — cache-path зафиксирован thread-ownership invariant |
| 3.1 | P1 | DRY | Исправлено 12.03.2026 — progress helper централизован в `preparation.py` |
| 3.2 | P1 | DRY | Исправлено 12.03.2026 — общая run-context логика вынесена в core-helper |
| 3.3 | P1 | Типизация | Исправлено 12.03.2026 — введён типизированный `AppConfig` |
| 3.4 | P1 | Архитектура | Исправлено 12.03.2026 — `process_document_images` переведён на `ImageProcessingContext` |
| 3.5 | P1 | Тестирование | Исправлено 12.03.2026 — добавлен `tests/test_document_pipeline.py` |
| 3.6 | P1 | Тестирование | Исправлено 12.03.2026 — добавлен `tests/test_app_runtime.py` |
| 3.7 | P1 | Баг | Исправлено 12.03.2026 — строка активности нормализована на `Блок` |
| 4.1 | P2 | Архитектура | Исправлено 12.03.2026 — dependency threading свернут в `ImageProcessingContext` |
| 4.2 | P2 | Архитектура | Исправлено 12.03.2026 — runtime reflection удалён, сигнатуры выровнены |
| 4.3 | P2 | Инфраструктура | Исправлено 12.03.2026 — добавлены `pyproject.toml` и `tests/conftest.py` |
| 4.4 | P2 | Архитектура | Исправлено 12.03.2026 — логгер переведён на lazy initialization |
| 4.5 | P2 | Память | Исправлено 12.03.2026 — `deepcopy` image-bytes заменён selective cloning |
| 5.1 | P3 | Типизация | Исправлено 12.03.2026 — добавлены `Protocol`-аннотации для seam'ов session state/upload |
| 5.2 | P3 | Читаемость | Исправлено 12.03.2026 — heuristic thresholds вынесены в именованные константы |
| 5.3 | P3 | Стиль | Исправлено 12.03.2026 — time/datetime разделены helper'ами по назначению |
| 5.4 | P3 | Типизация | Исправлено 12.03.2026 — введён `ImageMode(StrEnum)` |
| 5.5 | P3 | DRY | Исправлено 12.03.2026 — DOCX reading переиспользует `read_uploaded_file_bytes` |
| 5.6 | P3 | DRY | Исправлено 12.03.2026 — `is_retryable_error` вынесен в `image_shared.py` |
| 6.1 | P1 | Безопасность | Исправлено 12.03.2026 — добавлен document-level model-call budget |
| 6.2 | P1 | Безопасность | Исправлено 12.03.2026 — добавлен cleanup orphaned restart/completed files |
| 6.3 | P1 | Безопасность | Исправлено 12.03.2026 — HTML render обёрнут в trusted helper |
| 7.1 | P2 | Производительность | Исправлено 12.03.2026 — hot path переведён с `getpixel()` loops на byte-buffer scan |
| 7.2 | P2 | Производительность | Исправлено 12.03.2026 — registry TOML кэшируется через `lru_cache` |
| 7.3 | P2 | Производительность | Исправлено 12.03.2026 — preparation cache больше не копирует bytes целиком |
| 8.1 | P2 | Тестирование | Исправлено 12.03.2026 — добавлен `tests/conftest.py` |
| 8.2 | P2 | Тестирование | Исправлено 12.03.2026 — добавлен `tests/test_logger.py` |
| 8.3 | P2 | Тестирование | Исправлено 12.03.2026 — добавлен test на Pandoc integration seam |
| 9.1 | P3 | Документация | Исправлено 12.03.2026 — README дополнен `.env`-документацией |
| 9.2 | P3 | Документация | Исправлено 12.03.2026 — добавлен `CHANGELOG.md` |

### Новые замечания повторной верификации (исправлены 12.03.2026):

| # | Приоритет | Категория | Краткое описание |
|---|-----------|-----------|-----------------|
| 11.1 | P1 | Логика | Исправлено 12.03.2026 — stale duplicate render удалён из `_render_styled_matrix_table` |
| 11.2 | P1 | Логика | Исправлено 12.03.2026 — plain-table branch снова рендерит текст ячеек |
| 11.3 | P2 | Error Handling | Исправлено 12.03.2026 — vision validation fallback теперь логируется |
| 11.4 | P2 | Производительность | Исправлено 12.03.2026 — фон нормализуется через `Image.composite(...)` |
| 11.5 | P2 | Производительность | Исправлено 12.03.2026 — background sampling убрал `getpixel()` loops |
| 11.6 | P2 | Robustness | Исправлено 12.03.2026 — global `LOAD_TRUNCATED_IMAGES` override удалён |
| 11.7 | P2 | Дизайн | Исправлено 12.03.2026 — `extract_scene_graph` требует explicit client |
| 11.8 | P3 | Error Handling | Исправлено 12.03.2026 — `_read_uploaded_docx_bytes` сохраняет exception chain |
| 11.9 | P3 | Robustness | Исправлено 12.03.2026 — `ImageVariantCandidate.to_dict()` больше не отдаёт raw bytes |

---

## 12. Замечания третьей верификации (выявлены при глубоком повторном сканировании)

### 12.1. TOCTOU-гонка в `load_restart_source_bytes` — `FileNotFoundError` при конкурентном удалении

**Статус:** Исправлено 12.03.2026 — `exists()`/`is_file()` pre-check заменён на `try/except OSError` вокруг `read_bytes()`.

**Файл:** `restart_store.py`, функция `load_restart_source_bytes`
**Проблема:** Между вызовами `restart_path.exists()` и `restart_path.read_bytes()` файл мог быть удалён конкурентным вызовом `cleanup_stale_persisted_sources` или `clear_restart_source`. Это приводило к необработанному `FileNotFoundError`. При этом `clear_restart_source` в том же модуле корректно оборачивал файловые операции в `try/except OSError`.

**Исправление:** Убран pre-check, `read_bytes()` обёрнут в `try/except OSError: return None`.

### 12.2. `_store_persisted_source` — удаление старого файла до записи нового (data loss при ошибке записи)

**Статус:** Исправлено 12.03.2026 — порядок операций изменён на write-then-delete.

**Файл:** `restart_store.py`, функция `_store_persisted_source`
**Проблема:** `clear_restart_source(previous_source)` вызывался *до* `storage_path.write_bytes(source_bytes)`. При ошибке записи (disk full, permission denied) старый файл уже удалён, новый не создан — потеря данных restart source.

**Исправление:** Порядок операций изменён: сначала пишется новый файл, затем удаляется старый.

### 12.3. `normalize_model_output` — утечка language-тега при non-markdown code fence

**Статус:** Исправлено 12.03.2026 — парсинг code fence обобщён: при `\`\`\`` отрезается вся первая строка целиком.

**Файл:** `generation.py`, функция `normalize_model_output`
**Проблема:** Если модель оборачивала вывод в `` ```text `` или `` ```python `` (вместо `` ```markdown ``), `elif` ветка отрезала только три обратных кавычки, оставляя language-тег (`text`, `python` и т.д.) как спурious первую строку в возвращённом Markdown. Это контаминировало итоговый документ.

**Исправление:** При обнаружении `` ``` `` в начале строки отрезается всё до первого `\n`, чтобы надёжно удалить любой language-тег.

### 12.4. `call_responses_create_with_retry` — потеря финального retry при TypeError/timeout на последнем attempt

**Статус:** Исправлено 12.03.2026 — после выхода из цикла, если `timeout` был удалён, выполняется дополнительный вызов.

**Файл:** `image_shared.py`, функция `call_responses_create_with_retry`
**Проблема:** Если на последней итерации цикла `for attempt in range(1, max_retries + 1)` возникал `TypeError` о неподдерживаемом параметре `timeout`, код удалял параметр из payload и выполнял `continue`. Но итераций больше не оставалось, и функция падала в `RuntimeError("Responses retry loop exhausted unexpectedly.")`, хотя retry с исправленным payload ни разу не был попробован.

**Исправление:** После цикла добавлена проверка: если `timeout` был удалён во время цикла, выполняется финальный вызов API без `timeout`.

---

### Сводная таблица замечаний третьей верификации

| # | Приоритет | Категория | Краткое описание |
|---|-----------|-----------|-----------------|
| 12.1 | P2 | Robustness | Исправлено 12.03.2026 — `load_restart_source_bytes` TOCTOU-гонка закрыта try/except |
| 12.2 | P2 | Data Safety | Исправлено 12.03.2026 — `_store_persisted_source` write-then-delete вместо delete-then-write |
| 12.3 | P3 | Корректность | Исправлено 12.03.2026 — `normalize_model_output` надёжно отрезает language-тег |
| 12.4 | P3 | Robustness | Исправлено 12.03.2026 — retry loop даёт финальный вызов после удаления timeout |

---

## 13. Положительные стороны проекта

1. **Отличная декомпозиция.** Разделение на document → preparation → pipeline → generation → validation — чистое и понятное.
2. **Robust error handling.** Почти все внешние вызовы (OpenAI API, Pandoc, PIL) обёрнуты в try/except с осмысленными fallback'ами.
3. **Грамотная DOCX-валидация.** Zip-bomb protection, compression ratio check, entry count limit — хорошая security practice в `_validate_docx_archive`.
4. **Image pipeline resilience.** Multi-attempt semantic redraw с budget'ом, best-score selection, fallback cascade (reconstruction → creative → direct → safe) — индустриально зрелый подход.
5. **Typed events для worker communication.** `runtime_events.py` с `isinstance`-based dispatching — чисто и расширяемо.
6. **Тестовое покрытие image pipeline.** 115+ тестов для image-модулей — самая сложная часть проекта хорошо покрыта.
7. **Compare-all UX.** Генерация 3 вариантов с визуальным сравнением — продуманное решение для пользователя.
8. **Advisory vs Strict policy.** Гибкая стратегия валидации с возможностью soft-accept — хороший баланс quality vs usability.
9. **Все 31 замечание первоначального ревью исправлены.** Полное прохождение P0-P3 — свидетельство зрелого процесса разработки.

---

*Первоначальное ревью выполнено 12.03.2026 путём полного чтения всех ~7 500 строк продакшен-кода, ~3 000 строк тестов, конфигурационных файлов и спецификаций.*  
*Повторная верификация: все 31 исправление проверены, найдено 9 новых замечаний (2× P1, 5× P2, 2× P3).*  
*Третья верификация: все 9 замечаний 11.1–11.9 проверены и подтверждены как исправленные. Глубокое сканирование всех модулей: найдено 4 новых замечания (2× P2, 2× P3). Все 4 исправлены и подтверждены 204 тестами.*
