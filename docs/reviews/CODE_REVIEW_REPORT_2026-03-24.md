# Отчёт о ревью кода и архитектуры: DocxAICorrector

**Дата:** 2026-03-24  
**Ревьюер:** Kilo Code (anthropic/claude-sonnet-4.6)  
**Охват:** Все `.py` файлы корневого уровня, тесты, конфигурация  
**Предыдущие ревью:** `docs/archive/reviews/CODE_REVIEW_REPORT_2026-03-12.md`

---

## 0. Краткое резюме

Проект DocxAICorrector — Streamlit-приложение для AI-редактирования DOCX-документов через OpenAI Responses API. Пайплайн: загрузка DOCX/DOC -> разбор -> семантические блоки -> LLM-редактирование -> реинсерция изображений -> итоговый DOCX.

**Общая оценка:** Архитектура осознанная, с хорошей тестовой базой (~40 тест-файлов). Основные проблемы: дублирование логики парсинга ответа OpenAI между `generation.py` и `image_shared.py` (~70 строк), god-функции `run_document_processing` (~750 строк) и `main()` (~280 строк), несколько race conditions и нарушения границ слоёв.

**Итог по критичности:**
- Критических: 2
- Высоких: 5
- Средних: 8
- Низких: 9

---

## 1. Анализ по файлам


---

### 1.2 `config.py`

**Роль:** Загрузка `AppConfig` из TOML + env; создание и кэширование OpenAI-клиента. **Строк:** 467

| ID | Проблема | Категория | Влияние | Сложность |
|----|---------|-----------|---------|-----------|
| **C-02** | `get_client()` — глобальный `_CLIENT = None` без Lock. Два потока могут создать два клиента | Безопасность/Надёжность | Высокое | Низкая (30 мин) |
| C-03 | `load_app_config()` ~220 строк плоского парсинга для ~25 полей без абстракции | Дублирование | Среднее | Средняя |
| C-04 | `os.getenv(...).strip() or default_val` — inline, тогда как числовые поля используют `parse_X_env` | Несогласованность | Низкое | Низкая |
| C-05 | `OpenAI = None` как глобальная переменная — нестандартный ленивый кэш | Антипаттерн | Низкое | Низкая |

**Рекомендации:**
- **C-02:** Добавить `_CLIENT_LOCK = threading.Lock()` и DCL-паттерн (как в `processing_service.py`)
- **C-05:** Убрать `OpenAI = None`, импортировать из `openai` напрямую внутри `get_client()`

---

### 1.3 `generation.py`

**Роль:** Генерация Markdown через OpenAI Responses API; конвертация Markdown->DOCX через Pandoc; reference-документ для стилей. **Строк:** 1184

| ID | Проблема | Категория | Влияние | Сложность |
|----|---------|-----------|---------|-----------|
| **G-01** | Функции `_read_response_field` (334), `_coerce_response_text_value` (340), `_extract_text_from_content_item` (349) **полностью дублируют** одноимённые функции в `image_shared.py` (стр.80-102) | **Дублирование (критическое)** | КРИТИЧЕСКОЕ | Средняя |
| **G-02** | `_extract_response_output_text` (стр.359-415, ~56 строк) дублирует `extract_response_text` из `image_shared.py` | **Дублирование (критическое)** | КРИТИЧЕСКОЕ | Средняя |
| G-03 | `generate_markdown_block` (~130 строк): retry + prompt + парсинг + leakage + recovery в одной функции | Нарушение SRP | Среднее | Средняя |
| G-04 | Строки 721-723: дублированная ветка `raise recovery_exc` | Мёртвый код | Низкое | Низкая |
| G-05 | `@lru_cache` на `ensure_pandoc_available()` — кэширует ошибку навсегда | Антипаттерн | Среднее | Низкая |
| G-06 | `_SUPPORTED_RESPONSE_TEXT_TYPES` дублирует константу из `image_shared.py` | Дублирование | Низкое | Низкая |

**Рекомендации:**
- **G-01/G-02:** Удалить ~70 строк дублей; использовать `extract_response_text` из `image_shared.py`
- **G-04:** Упростить до одного `raise recovery_exc`
- **G-05:** Заменить `@lru_cache` на `_PANDOC_CHECKED: bool = False`-guard
- **G-06:** Удалить дубль константы из `generation.py`

---

### 1.4 `document.py`

**Роль:** Извлечение контента из DOCX, классификация абзацев, построение блоков и заданий. **Строк:** 1228

| ID | Проблема | Категория | Влияние | Сложность |
|----|---------|-----------|---------|-----------|
| D-01 | `extract_paragraph_units_from_docx` и `extract_inline_images` — публичные обёртки нигде не используются в продакшен-коде | Мёртвый код | Низкое | Низкая |
| D-02 | `_read_uploaded_docx_bytes` вызывает `normalize_uploaded_document` — потенциальная двойная нормализация | Дублирование | Среднее | Средняя |
| D-03 | `build_semantic_blocks` (~87 строк): цикломатическая сложность >15, 6+ уровней вложенности | Сложность | Среднее | Высокая |
| D-04 | `_resolve_num_pr_details` (~78 строк): вложенные циклы, множество ранних `return` | Сложность | Среднее | Высокая |
| D-05 | `COMPARE_ALL_VARIANT_LABELS` и `MANUAL_REVIEW_SAFE_LABEL` — UI-метки в слое Document | Нарушение архитектуры | Низкое | Низкая |
| D-06 | `formatting_transfer.py` импортирует 8 приватных функций `document.py` с `_` prefix | Нарушение инкапсуляции | Среднее | Средняя |

**Рекомендации:**
- **D-01:** Удалить или явно пометить как `# test-only`
- **D-03:** Выделить предикаты `_should_flush_before_paragraph()`, `_should_append_paragraph()`
- **D-05:** Переместить `COMPARE_ALL_VARIANT_LABELS` в `models.py`
- **D-06:** Сделать используемые функции публичными или вынести в `docx_xml_utils.py`

---

### 1.5 `image_shared.py` — без критических замечаний

Файл чистый. Константа `_SUPPORTED_RESPONSE_TEXT_TYPES` дублируется в `generation.py` (см. G-06).

---

### 1.6 `app.py`

**Роль:** Точка входа Streamlit; оркестрация UI flow. **Строк:** 487

| ID | Проблема | Категория | Влияние | Сложность |
|----|---------|-----------|---------|-----------|
| A-01 | `main()` — ~280 строк, 5 уровней вложенности: инициализация + orchestration + UI в одной функции | God-Function | Высокое | Высокая |
| A-02 | Импорты из `application_flow` внутри тела `main()` (стр.319-325) — нарушение PEP 8 | Стиль | Низкое | Низкая |
| A-03 | `_mark_app_ready()` и `_schedule_stale_persisted_sources_cleanup()` в 8+ местах | DRY-нарушение | Низкое | Низкая |
| A-04 | Двойной guard `_CLEANUP_THREAD_STARTED` + `session_state.persisted_source_cleanup_done` | Антипаттерн | Низкое | Низкая |

**Рекомендации:**
- **A-01:** Разбить на `_handle_processing_active()`, `_handle_preparation_active()`, `_handle_file_selected_ready()`, `_handle_idle_state()`
- **A-03:** Создать `_finalize_app_frame()` и вызывать перед каждым `return`

---

### 1.7 `document_pipeline.py`

**Роль:** Оркестрация: блоки -> LLM -> изображения -> DOCX сборка. **Строк:** 1162

| ID | Проблема | Категория | Влияние | Сложность |
|----|---------|-----------|---------|-----------|
| **DP-01** | `run_document_processing` — ~750 строк, 6 фаз в одной функции. Нетестируема изолированно | **God-Function (критическое)** | КРИТИЧЕСКОЕ | Высокая |
| DP-02 | Паттерн `emit_state + emit_finalize + emit_activity + emit_log + return "failed"` повторяется 8+ раз | Дублирование | Среднее | Средняя |
| DP-03 | `FORMATTING_DIAGNOSTICS_DIR` дублируется в `formatting_transfer.py` | Дублирование | Низкое | Низкая |
| DP-04 | `_call_docx_restorer_with_optional_registry` — `try/except TypeError` костыль | Устаревший код | Среднее | Низкая |

**Рекомендации:**
- **DP-01:** Разбить: `_run_block_loop()`, `_run_image_phase()`, `_run_docx_assembly()`
- **DP-02:** Хелпер `_emit_failure(runtime, ...) -> "failed"`
- **DP-03:** Вынести `FORMATTING_DIAGNOSTICS_DIR` в `constants.py`

---

### 1.8 `processing_service.py`

**Строк:** 288

| ID | Проблема | Категория | Влияние |
|----|---------|-----------|---------|
| PSV-01 | `ProcessingService` — датакласс с 28 полями-callable, почти все с единственной реальной реализацией | Избыточная абстракция | Среднее |
| PSV-02 | `run_document_processing` передаёт 18 kwargs | Читаемость | Среднее |
| PSV-03 | `reset_processing_service()` нигде не используется в продакшен-коде | Потенциальный мёртвый код | Низкое |

**Рекомендация PSV-01:** Сгруппировать в `EmitterDependencies`, `ImageDependencies`, `GenerationDependencies` — снизит 28 полей до ~10.

---

### 1.9 `processing_runtime.py`

**Строк:** 771

| ID | Проблема | Категория | Влияние | Сложность |
|----|---------|-----------|---------|-----------|
| PR-01 | `_reset_image_state()` напрямую записывает в `st.session_state` — инфраструктурный модуль зависит от UI-фреймворка | Нарушение архитектуры | Среднее | Низкая |
| **PR-02** | `_build_default_image_processing_summary()` **полностью дублирует** `_default_image_processing_summary()` из `state.py` | **Дублирование** | Среднее | Низкая |
| PR-03 | `drain_processing_events` — 65-строчный if-elif. Добавление события требует изменений в 3 местах | Поддерживаемость | Среднее | Средняя |

**Рекомендации:**
- **PR-01:** Передавать `reset_image_state_fn` как параметр
- **PR-02:** Одна реализация в `state.py`, импортировать оттуда
- **PR-03:** Метод `apply(session)` у каждого event-датакласса (visitor pattern)

---

### 1.10 `state.py`

**Строк:** 254

| ID | Проблема | Категория | Влияние |
|----|---------|-----------|---------|
| ST-01 | `init_session_state` и `reset_run_state` дублируют список полей session_state | Дублирование | Среднее |
| ST-02 | `_current_unix_timestamp()` — однострочная обёртка над `time.time()` без ценности | Мёртвый код | Низкое |

**Рекомендация ST-01:** Единый `_SESSION_STATE_DEFAULTS: dict` с фабриками значений.

---

### 1.11 `app_runtime.py` — запах Middle Man

**Строк:** 125. Все функции — однострочные обёртки. Запах «Middle Man» — неясна ценность этого слоя.
**Рекомендация:** Рассмотреть слияние с `processing_runtime.py`.

---

### 1.12 `preparation.py`

**Строк:** 298

| ID | Проблема | Категория |
|----|---------|-----------|
| PRP-01 | `_build_in_memory_uploaded_file` дублирует `build_in_memory_uploaded_file` из `processing_runtime.py` | Дублирование |
| PRP-02 | Глобальные mutable синглтоны кэша усложняют тест-изоляцию | Тестируемость |

**Рекомендации:** PRP-01: использовать из `processing_runtime.py`. PRP-02: инкапсулировать в класс `PreparationCache`.

---

### 1.13 `logger.py`

**Строк:** 200. `format_user_error` — 30+ if-else веток по статус-коду и классу исключения.
**Рекомендация:** Заменить на словари `_STATUS_CODE_MESSAGES: dict[int, str]` + `_EXCEPTION_CLASS_MESSAGES: dict[str, str]`.

---

### 1.14 `formatting_transfer.py`

**Строк:** 1023. Импортирует 8 приватных функций `document.py` (нарушение инкапсуляции, см. D-06). `FORMATTING_DIAGNOSTICS_DIR` дублируется (см. DP-03).

---

### 1.15 `models.py`

**Строк:** 245. `ImageAsset.redrawn_mime_type` дублирует `metadata.rendered_mime_type`. `sync_pipeline_metadata` синхронизирует вручную — риск рассинхронизации.
**Рекомендация:** Удалить `redrawn_mime_type`, использовать `metadata.rendered_mime_type`.

---

### 1.16 Прочие файлы

| Файл | Оценка |
|------|--------|
| `workflow_state.py` (30 строк) | Образцово чистый — без замечаний |
| `runtime_events.py` (70 строк) | Чистый; Union-type требует ручного обновления при добавлении события |
| `restart_store.py` (121 строка) | Чистый |
| `compare_panel.py` (27 строк) | Чистый |
| `ui.py` (~668 строк) | Зависимость от `st.session_state` снижает тестируемость |
| `image_pipeline.py`, `image_generation.py` | Без критических нарушений в осмотренных фрагментах |

---

## 2. Архитектурный обзор

### 2.1 Слои и их соблюдение

```
UI Layer:          app.py  ui.py  compare_panel.py
Orchestration:     application_flow.py  app_runtime.py
Pipeline/Domain:   document_pipeline.py  processing_service.py  preparation.py
Feature Modules:   generation.py  document.py  formatting_transfer.py  image_*.py
Infrastructure:    processing_runtime.py  state.py  restart_store.py  logger.py  config.py
Models/Events:     models.py  runtime_events.py  workflow_state.py  constants.py
```

**Нарушения границ слоёв:**

1. `processing_runtime.py` (Infrastructure) -> `st.session_state` (UI) — прямая зависимость снизу вверх
2. `formatting_transfer.py` (Feature) -> приватные функции `document.py`
3. `document.py` (Feature) -> UI-метки `COMPARE_ALL_VARIANT_LABELS`

### 2.2 Сводная таблица дублирований

| Дублирование | Файлы | Строк | Рекомендация |
|---|---|---|---|
| Парсинг OpenAI-ответа (3 функции) | `generation.py` / `image_shared.py` | ~70 | Удалить из `generation.py` |
| `_default_image_processing_summary` | `state.py` / `processing_runtime.py` | ~10 | Одна реализация в `state.py` |
| `_build_in_memory_uploaded_file` | `preparation.py` / `processing_runtime.py` | ~5 | Использовать из `processing_runtime.py` |
| `FORMATTING_DIAGNOSTICS_DIR` | `document_pipeline.py` / `formatting_transfer.py` | 1 | Вынести в `constants.py` |
| `_SUPPORTED_RESPONSE_TEXT_TYPES` | `generation.py` / `image_shared.py` | 1 | Одна константа в `image_shared.py` |

### 2.3 Coupling / Cohesion

**Высокое coupling (god-модули):**
- `document_pipeline.py` — 14+ внешних зависимостей через Protocol-инъекции
- `processing_service.py` — 28-польный датакласс зависимостей
- `app.py::main()` — вызовы из 10+ модулей

**Хорошо изолированы:**
`workflow_state.py`, `runtime_events.py`, `constants.py`, `restart_store.py`, `image_shared.py`

---

## 3. Приоритеты изменений

### Критические

| ID | Описание | Файл | Усилий |
|----|---------|------|--------|
| G-01/G-02 | Дублирование ~70 строк парсинга ответа | `generation.py` | 2-4 ч |
| C-02 | Race condition в `get_client()` без Lock | `config.py` | 30 мин |

### Высокие

| ID | Описание | Файл | Усилий |
|----|---------|------|--------|
| PR-02 | Дублирование `_default_image_processing_summary` | `processing_runtime.py` | 30 мин |
| DP-01 | Разбить `run_document_processing` (~750 строк) | `document_pipeline.py` | 1-2 дня |
| A-01 | Разбить `main()` (~280 строк) | `app.py` | 4-8 ч |
| DP-02 | Хелпер `_emit_failure()` для 8 блоков | `document_pipeline.py` | 2-3 ч |
| FT-01/D-06 | Публичные функции `document.py` | `document.py` | 1-2 ч |

### Средние

| ID | Описание | Усилий |
|----|---------|--------|
| ST-01 | Единый словарь дефолтов session_state | 2-3 ч |
| PRP-01 | Удалить дубль `_build_in_memory_uploaded_file` | 30 мин |
| DP-03/FT-02 | `FORMATTING_DIAGNOSTICS_DIR` в `constants.py` | 30 мин |
| D-05 | UI-метки из `document.py` в `models.py` | 30 мин |
| G-05 | Исправить `@lru_cache` для `ensure_pandoc_available` | 30 мин |
| MD-01 | Удалить `redrawn_mime_type` из `ImageAsset` | 1-2 ч |
| G-06/IS-01 | Убрать дубль `_SUPPORTED_RESPONSE_TEXT_TYPES` | 15 мин |
| C-03 | Рефактор `load_app_config` (группировка) | 4-8 ч |

### Низкие

| ID | Описание |
|----|---------|
| D-01 | Удалить/пометить мёртвые обёртки `document.py` |
| G-04 | Упростить дублированный `raise recovery_exc` |
| ST-02 | Удалить `_current_unix_timestamp()` |
| A-02 | Вынести late-импорты в начало `app.py` |
| A-03 | Единый `_finalize_app_frame()` |
| C-05 | Убрать `OpenAI = None` |
| AR-01 | Рассмотреть слияние `app_runtime.py` |
| PSV-01 | Группировка полей `ProcessingService` |
| PSV-03 | Проверить нужность `reset_processing_service()` |

---

## 4. План миграции

### Спринт 1: Быстрые победы (~4 ч, 1 PR)

Все задачи независимы (выполнять параллельно):

2. **C-02** — Добавить `threading.Lock()` в `get_client()`
3. **PR-02** — Удалить дубль `_default_image_processing_summary` в `processing_runtime.py`
4. **PRP-01** — Удалить `_build_in_memory_uploaded_file` из `preparation.py`
5. **DP-03/FT-02** — Вынести `FORMATTING_DIAGNOSTICS_DIR` в `constants.py`
6. **G-06/IS-01** — Убрать дубль `_SUPPORTED_RESPONSE_TEXT_TYPES` из `generation.py`
7. **D-05** — Переместить `COMPARE_ALL_VARIANT_LABELS` в `models.py`
8. **G-04, ST-02** — Мелкий мёртвый код

**Тесты регрессии:**
```bash
pytest tests/test_config.py tests/test_state.py tests/test_processing_runtime.py tests/test_generation.py -v
```

**Ожидаемый эффект:** -~100 строк дублирующего кода, устранение race condition, рабочие имена моделей.
**Регрессионный риск:** Минимальный.

---

### Спринт 2: Критическое дублирование G-01/G-02 (~4-6 ч, 1 PR)

Зависимость: Спринт 1 выполнен.

1. Параметризовать `extract_response_text` из `image_shared.py` для нужд generation
2. Удалить `_read_response_field`, `_coerce_response_text_value`, `_extract_text_from_content_item` из `generation.py`
3. Удалить `_extract_response_output_text` из `generation.py` (~70 строк total)
4. Убедиться в идентичности поведения при `empty_response`, `collapsed_output`, `incomplete_response`

**Тесты регрессии:**
```bash
pytest tests/test_generation.py tests/test_image_generation.py tests/test_image_analysis.py tests/test_image_validation.py -v
```

---

### Спринт 3: Рефактор `document_pipeline.py` (~1-2 дня, 1 PR)

Зависимость: Спринт 1 выполнен.

1. Создать `_emit_failure(runtime, *, code, title, detail, ...) -> "failed"`
2. Разбить: `_run_block_loop()`, `_run_image_phase()`, `_run_docx_assembly()`
3. Перенести функции диагностики форматирования в `formatting_transfer.py`
4. Unit-тест для каждой новой фазы

**Тесты регрессии:**
```bash
pytest tests/test_document_pipeline.py tests/test_real_document_pipeline_validation.py -v
```

---

### Спринт 4: Рефактор `app.py::main()` (~4-8 ч, 1 PR)

Зависимость: Спринт 1 выполнен.

1. Разбить на `_handle_processing_active()`, `_handle_preparation_active()`, `_handle_file_selected_ready()`, `_handle_idle_state()`
2. Вынести все импорты на верх файла
3. Создать `_finalize_app_frame()`

**Тесты регрессии:**
```bash
pytest tests/test_app.py -v
```

---

### Спринт 5: Долгосрочная очистка (~2-3 дня)

1. Единый `_SESSION_STATE_DEFAULTS` dict (ST-01)
2. Публичные функции `document.py` (D-06/FT-01)
3. Класс `PreparationCache` (PRP-02)
4. dict-dispatch в `format_user_error` (LG-01)
5. `_reset_image_state` без `st.session_state` (PR-01)

---

## 5. Требования к тестированию

### По спринтам

| Спринт | Тест-файлы для регрессии |
|--------|--------------------------|
| 1 | `test_config.py`, `test_state.py`, `test_processing_runtime.py`, `test_generation.py` |
| 2 | `test_generation.py`, `test_image_generation.py`, `test_image_analysis.py`, `test_image_validation.py` |
| 3 | `test_document_pipeline.py`, `test_real_document_pipeline_validation.py` |
| 4 | `test_app.py` |

### Новые тесты (proposals)

**После Спринта 1 — thread-safety `get_client()`:**
```python
def test_get_client_thread_safety():
    import threading
    clients = []
    def _get(): clients.append(get_client())
    threads = [threading.Thread(target=_get) for _ in range(4)]
    for t in threads: t.start()
    for t in threads: t.join()
    assert len(set(id(c) for c in clients)) == 1
```

**После Спринта 2 — консистентность парсинга:**
```python
def test_response_parser_consistency_with_image_shared():
    """generation и image_shared должны одинаково обрабатывать edge-cases."""
    from image_shared import extract_response_text
    # проверить совпадение при empty/collapsed/incomplete response
```

**После Спринта 3 — изолированные фазы:**
```python
def test_run_block_loop_stops_on_stop_signal():
    ...

def test_emit_failure_returns_failed_string():
    ...
```

---

## 6. Метрики качества (цели)

| Метрика | Текущее | Цель после рефакторов |
|--------|---------|----------------------|
| Дублирующие строки (парсинг OpenAI) | ~70 | 0 |
| Длина `run_document_processing` (строк) | ~750 | <=200 |
| Длина `main()` в `app.py` (строк) | ~280 | <=80 |
| Длина `load_app_config()` (строк) | ~220 | <=120 |
| Полей в `ProcessingService` | 28 | <=12 (с группировкой) |
| Глобальные mutable синглтоны без Lock | 2 | 0 |
| Нарушения границ слоёв | 3 | 0 |

---

## 7. Итоговые выводы

### Сильные стороны (не трогать)

- Надёжная retry-логика с backoff, recovery, leakage-detection в `generation.py`
- Хорошая тестовая база (~40 файлов, ~200+ тестов)
- Безопасная валидация DOCX-архивов (zip-bomb, path traversal, entry count)
- Чёткое разделение фоновых потоков от Streamlit-сессии через event queues
- `workflow_state.py`, `runtime_events.py`, `restart_store.py` — образцово чистые модули

### Главные проблемы

1. **Несуществующие имена моделей** в `constants.py` — приложение с дефолтами не работает
2. **Дублирование ~70 строк** парсинга OpenAI-ответа между `generation.py` и `image_shared.py`
3. **Race condition** в `get_client()` — без Lock
4. **God-функции** `run_document_processing` (~750 строк) и `main()` (~280 строк)
5. **Нарушения границ слоёв** — инфраструктура зависит от UI (3 места)

### Рекомендованная последовательность

**Спринт 1** (быстрые победы, минимальный риск) -> **Спринт 2** (критическое дублирование) -> **Спринты 3-4** (структурный рефактор) -> **Спринт 5** (долгосрочная очистка).

---

## 8. Машиночитаемый формат (YAML)

```yaml
review:
  date: "2026-03-24"
  reviewer: "Kilo Code (anthropic/claude-sonnet-4.6)"
  project: "DocxAICorrector"
  summary:
    total_issues: 24
    critical: 2
    high: 5
    medium: 8
    low: 9

issues:
    regression_risk: minimal
  - id: G-01
    file: generation.py
    lines: "334-356"
    description: "Дублирование _read_response_field, _coerce_response_text_value, _extract_text_from_content_item из image_shared.py"
    category: duplication
    priority: critical
    effort_hours: 2.0
    sprint: 2
    regression_risk: medium
    duplicate_of: "image_shared.py:80-102"
  - id: G-02
    file: generation.py
    lines: "359-415"
    description: "Дублирование _extract_response_output_text (~56 строк) из image_shared.extract_response_text"
    category: duplication
    priority: critical
    effort_hours: 2.0
    sprint: 2
    regression_risk: medium
    duplicate_of: "image_shared.py:105-161"
  - id: C-02
    file: config.py
    function: get_client
    description: "Race condition при инициализации _CLIENT - нет Lock"
    category: reliability
    priority: critical
    effort_hours: 0.5
    sprint: 1
    regression_risk: minimal
  - id: PR-02
    file: processing_runtime.py
    description: "Дублирование _build_default_image_processing_summary из state.py"
    category: duplication
    priority: high
    effort_hours: 0.5
    sprint: 1
    regression_risk: minimal
    duplicate_of: "state.py:41-49"
  - id: DP-01
    file: document_pipeline.py
    function: run_document_processing
    description: "God-function ~750 строк - 6 фаз в одной функции"
    category: architecture_violation
    priority: high
    effort_hours: 12.0
    sprint: 3
    regression_risk: medium
  - id: A-01
    file: app.py
    function: main
    description: "God-function ~280 строк"
    category: architecture_violation
    priority: high
    effort_hours: 6.0
    sprint: 4
    regression_risk: low
  - id: DP-02
    file: document_pipeline.py
    description: "emit_state+emit_finalize+emit_activity повторяется 8+ раз"
    category: duplication
    priority: high
    effort_hours: 2.0
    sprint: 3
    regression_risk: low
  - id: FT-01
    files: [document.py, formatting_transfer.py]
    description: "formatting_transfer.py импортирует 8 приватных функций document.py"
    category: architecture_violation
    priority: high
    effort_hours: 1.5
    sprint: 5
    regression_risk: low

  - id: ST-01
    file: state.py
    description: "init_session_state и reset_run_state дублируют список полей"
    category: duplication
    priority: medium
    effort_hours: 2.0
    sprint: 5
    regression_risk: low
  - id: PRP-01
    file: preparation.py
    function: _build_in_memory_uploaded_file
    description: "Дублирует build_in_memory_uploaded_file из processing_runtime.py"
    category: duplication
    priority: medium
    effort_hours: 0.5
    sprint: 1
    regression_risk: minimal
  - id: DP-03
    files: [document_pipeline.py, formatting_transfer.py]
    description: "FORMATTING_DIAGNOSTICS_DIR определена в двух местах"
    category: duplication
    priority: medium
    effort_hours: 0.5
    sprint: 1
    regression_risk: minimal
  - id: D-05
    file: document.py
    description: "COMPARE_ALL_VARIANT_LABELS - UI-метки в слое Document"
    category: architecture_violation
    priority: medium
    effort_hours: 0.5
    sprint: 1
    regression_risk: minimal
  - id: G-05
    file: generation.py
    function: ensure_pandoc_available
    description: "@lru_cache кэширует ошибку навсегда"
    category: antipattern
    priority: medium
    effort_hours: 0.5
    sprint: 1
    regression_risk: minimal
  - id: MD-01
    file: models.py
    class: ImageAsset
    description: "redrawn_mime_type дублирует metadata.rendered_mime_type"
    category: duplication
    priority: medium
    effort_hours: 1.5
    sprint: 5
    regression_risk: medium
  - id: G-06
    file: generation.py
    description: "_SUPPORTED_RESPONSE_TEXT_TYPES дублирует константу из image_shared.py"
    category: duplication
    priority: medium
    effort_hours: 0.25
    sprint: 1
    regression_risk: minimal
  - id: C-03
    file: config.py
    function: load_app_config
    description: "220-строчная плоская функция без абстракции"
    category: readability
    priority: medium
    effort_hours: 6.0
    sprint: 5
    regression_risk: low
  - id: D-01
    file: document.py
    functions: [extract_paragraph_units_from_docx, extract_inline_images]
    description: "Публичные обёртки нигде не используются в продакшен-коде"
    category: dead_code
    priority: low
    effort_hours: 0.5
    sprint: 1
    regression_risk: minimal
  - id: G-04
    file: generation.py
    lines: "721-723"
    description: "Дублированная ветка raise recovery_exc"
    category: dead_code
    priority: low
    effort_hours: 0.25
    sprint: 1
    regression_risk: minimal
  - id: ST-02
    file: state.py
    function: _current_unix_timestamp
    description: "Обёртка над time.time() без значимости"
    category: dead_code
    priority: low
    effort_hours: 0.25
    sprint: 1
    regression_risk: minimal

sprints:
  - sprint: 1
    name: "Быстрые победы"
    estimated_hours: 4
    issues: [C-02, PR-02, PRP-01, DP-03, G-06, D-05, G-05, G-04, ST-02, D-01]
    expected_lines_removed: 80
    regression_risk: minimal
  - sprint: 2
    name: "Критическое дублирование"
    estimated_hours: 5
    issues: [G-01, G-02]
    expected_lines_removed: 70
    regression_risk: medium
  - sprint: 3
    name: "Рефактор document_pipeline"
    estimated_hours: 14
    issues: [DP-01, DP-02]
    expected_lines_removed: 550
    regression_risk: medium
  - sprint: 4
    name: "Рефактор app.py main()"
    estimated_hours: 6
    issues: [A-01]
    expected_lines_removed: 200
    regression_risk: low
  - sprint: 5
    name: "Долгосрочная очистка"
    estimated_hours: 20
    issues: [ST-01, FT-01, MD-01, C-03, PRP-02]
    expected_lines_removed: 150
    regression_risk: low

metrics:
  current:
    duplicated_openai_parser_lines: 70
    run_document_processing_lines: 750
    main_function_lines: 280
    load_app_config_lines: 220
    processing_service_fields: 28
    global_singletons_without_lock: 2
    layer_boundary_violations: 3
  target:
    duplicated_openai_parser_lines: 0
    run_document_processing_lines: 200
    main_function_lines: 80
    load_app_config_lines: 120
    processing_service_fields: 12
    global_singletons_without_lock: 0
    layer_boundary_violations: 0
```

---

*Конец отчёта. Дата генерации: 2026-03-24.*