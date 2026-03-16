# Code Review Remediation Spec — DocxAICorrector
**Дата:** 2026-03-16  
**Источник:** End-to-end code review всего пайплайна (загрузка → парсинг → генерация → финализация DOCX)  
**Статус:** DRAFT — требует приёмки

---

## Содержание

1. [Контекст и допущения](#1-контекст-и-допущения)
2. [Карта пайплайна](#2-карта-пайплайна)
3. [Фаза 0 — Немедленные hotfix (P0)](#3-фаза-0--немедленные-hotfix-p0)
4. [Фаза 1 — Корректность данных (P1)](#4-фаза-1--корректность-данных-p1)
5. [Фаза 2 — Архитектурная надёжность (P2)](#5-фаза-2--архитектурная-надёжность-p2)
6. [Фаза 3 — Производительность и наблюдаемость (P3)](#6-фаза-3--производительность-и-наблюдаемость-p3)
7. [Критерии завершения](#7-критерии-завершения)
8. [Полный реестр проблем](#8-полный-реестр-проблем)

---

## 1. Контекст и допущения

### 1.1 Scope

Ревью охватывает следующие модули в порядке вызова:

```
app.py
  └─ application_flow.py          (preparation)
       └─ preparation.py
            └─ document.py         (parse, extract, rebuild)
  └─ processing_runtime.py        (background worker infra)
  └─ document_pipeline.py         (main processing loop)
       └─ generation.py            (LLM call, markdown→docx)
       └─ image_pipeline.py        (image AI pipeline)
            └─ image_analysis.py
            └─ image_generation.py
            └─ image_reconstruction.py
            └─ image_validation.py
            └─ image_pipeline_policy.py
  └─ processing_service.py        (DI wrapper)
  └─ state.py / workflow_state.py
  └─ restart_store.py
  └─ config.py / constants.py / models.py / logger.py
```

### 1.2 Допущения

- Python 3.12+, WSL Debian, python-docx 1.x, lxml 5.x, Streamlit 1.x.
- Приложение работает в однопользовательском или малонагруженном режиме; race-условия актуальны при нескольких вкладках браузера.
- Тесты существуют в `tests/`, запускаются через `bash scripts/test.sh`.
- OpenAI Responses API используется вместо стандартного Chat Completions.

---

## 2. Карта пайплайна

```
[User Upload]
      │
      ▼
app.py: _is_uploaded_file_too_large()          — проверка размера до чтения
      │  ← BUG: Streamlit не ограничивает maxUploadSize; проверка наступает поздно (SEC-01)
      ▼
_start_background_preparation()
      │
      ▼
application_flow.prepare_run_context_for_background()
      │
      ▼
preparation.prepare_document_for_processing()   — кэш (session + shared)
      │
      ▼
document.extract_document_content_from_docx()
    ├─ _read_uploaded_docx_bytes()
    ├─ _validate_docx_archive()               — zip-bomb, size, entry count
    │     ← ARCH: zip-slip не проверяется (SEC-02)
    ├─ _iter_document_block_items()
    ├─ _build_paragraph_unit()
    ├─ _build_table_unit()
    └─ _reclassify_adjacent_captions()
      │
      ▼
document.build_semantic_blocks() → build_editing_jobs()
      │
      ▼
[Processing Worker Thread]
      │
      ▼
document_pipeline.run_document_processing()
    ├─ get_client() / ensure_pandoc() / load_system_prompt()
    ├─ for each job:
    │     generation.generate_markdown_block()  ← LLM call (Responses API)
    │     └─ BUG: нет max_output_tokens (BUG-12)
    ├─ image_pipeline.process_document_images()
    │     ├─ image_analysis.analyze_image()
    │     │     └─ image_shared.call_responses_create_with_retry()
    │     │           ← BUG: бюджет считается на упавших попытках (BUG-05)
    │     ├─ image_generation.generate_image_candidate()
    │     │     ├─ _generate_reconstructed_candidate()
    │     │     │     └─ image_reconstruction.extract_scene_graph()
    │     │     │           ← BUG: нет retry/timeout, pre-consume бюджета (BUG-06)
    │     │     └─ _generate_semantic_candidate()  ← до 4 fallback AI-вызовов (ARCH-04)
    │     └─ image_validation.validate_redraw_result()
    │           ← BUG: parse_json_object strip("`") корruptирует JSON (BUG-01)
    ├─ inspect_placeholder_integrity()
    ├─ generation.convert_markdown_to_docx_bytes()  — pandoc
    ├─ document.preserve_source_paragraph_properties()
    │     └─ BUG: zip() без диагностики при несоответствии (BUG-03)
    ├─ document.normalize_semantic_output_docx()
    │     └─ BUG: zip() без диагностики при несоответствии (BUG-03)
    └─ document.reinsert_inline_images()
          └─ BUG: _replace_xml_element_with_sequence удаляет без замены (BUG-02)
      │
      ▼
[Result → st.session_state → restart_store → UI]
    └─ restart_store: ← BUG: небезопасные символы в именах файлов (BUG-09)
```

---

## 3. Фаза 0 — Немедленные hotfix (P0)

Эти изменения устраняют баги, которые приводят к потере данных, OOM или молчаливой порче результата. Выполняются в первую очередь, без рефакторинга вокруг.

---

### FIX-01 · `parse_json_object` — исправить strip backtick

**Файл:** `image_shared.py`  
**Приоритет:** P0  
**Тест:** `tests/test_image_analysis.py`, `tests/test_image_validation.py`

#### Текущий код (строки ≈48-56)

```python
def parse_json_object(raw_text: str, *, empty_message: str, no_json_message: str) -> dict[str, object]:
    text = raw_text.strip()
    if not text:
        raise RuntimeError(empty_message)
    if text.startswith("```"):
        text = text.strip("`")          # ← БАГО: strip(chars), не strip(prefix)
        if text.lower().startswith("json"):
            text = text[4:].strip()
```

**Проблема:** `str.strip(chars)` удаляет *все* символы из набора `chars` с обоих концов. Если `extracted_text` содержит `` ` `` (код, формула), JSON обрезается до невалидного состояния → `JSONDecodeError` → полный fallback image validation.

#### Целевой код

```python
def parse_json_object(raw_text: str, *, empty_message: str, no_json_message: str) -> dict[str, object]:
    text = raw_text.strip()
    if not text:
        raise RuntimeError(empty_message)
    if text.startswith("```"):
        first_newline = text.find("\n")
        if first_newline != -1:
            text = text[first_newline + 1:]
            last_fence = text.rfind("```")
            if last_fence != -1:
                text = text[:last_fence]
            text = text.strip()
        else:
            text = text[3:].strip()
            if text.endswith("```"):
                text = text[:-3].strip()
```

#### Тесты (добавить в `tests/test_image_analysis.py`)

```python
def test_parse_json_object_with_backtick_in_content():
    from image_shared import parse_json_object
    raw = '```json\n{"key": "val`ue"}\n```'
    result = parse_json_object(raw, empty_message="empty", no_json_message="nojson")
    assert result == {"key": "val`ue"}

def test_parse_json_object_fence_without_newline():
    from image_shared import parse_json_object
    raw = '```{"key": 1}```'
    result = parse_json_object(raw, empty_message="empty", no_json_message="nojson")
    assert result == {"key": 1}
```

---

### FIX-02 · `_replace_xml_element_with_sequence` — guard при пустом списке замен

**Файл:** `document.py`  
**Приоритет:** P0  
**Тест:** `tests/test_document.py`

#### Текущий код

```python
def _replace_xml_element_with_sequence(element, replacements) -> None:
    parent = element.getparent()
    if parent is None:
        return
    anchor = element
    for replacement in replacements:
        anchor.addnext(replacement)
        anchor = replacement
    parent.remove(element)    # ← удаляет элемент даже если replacements = []
```

**Проблема:** При пустом `replacements` цикл не выполняется, `element` удаляется без вставки замены → молчаливая потеря run-элемента DOCX с текстом.

#### Целевой код

```python
def _replace_xml_element_with_sequence(element, replacements) -> None:
    if not replacements:
        return
    parent = element.getparent()
    if parent is None:
        return
    anchor = element
    for replacement in replacements:
        anchor.addnext(replacement)
        anchor = replacement
    parent.remove(element)
```

#### Тест (добавить в `tests/test_document.py`)

```python
def test_replace_xml_element_with_sequence_empty_replacements_is_noop():
    """Функция не должна удалять элемент если список замен пуст."""
    from lxml import etree
    from document import _replace_xml_element_with_sequence

    parent = etree.fromstring("<root><child>text</child></root>")
    child = parent[0]
    _replace_xml_element_with_sequence(child, [])
    assert len(parent) == 1  # child не удалён
    assert parent[0].text == "text"
```

---

### FIX-03 · `.streamlit/config.toml` — ограничить maxUploadSize

**Файл:** `.streamlit/config.toml`  
**Приоритет:** P0  
**Тест:** ручная проверка / `tests/test_startup_performance_contract.py`

**Проблема:** Streamlit по умолчанию принимает файлы до 200MB. Проверка `MAX_DOCX_ARCHIVE_SIZE_BYTES` происходит только после полного чтения файла в память (`_read_uploaded_docx_bytes` → `_validate_docx_archive`). При 200MB-файлах возможен OOM.

#### Изменение

В файл `.streamlit/config.toml` добавить (или убедиться, что присутствует):

```toml
[server]
maxUploadSize = 25
```

> 25 соответствует `MAX_DOCX_ARCHIVE_SIZE_BYTES = 25 * 1024 * 1024`.

Значение должно соответствовать `constants.py::MAX_DOCX_ARCHIVE_SIZE_BYTES / (1024 * 1024)`. Это соответствие нигде не документировано — добавить комментарий в `constants.py`.

---

### FIX-04 · Дедупликация `MAX_DOCX_ARCHIVE_SIZE_BYTES`

**Файлы:** `document.py`, `constants.py`  
**Приоритет:** P0

**Проблема:** `MAX_DOCX_ARCHIVE_SIZE_BYTES` объявлена независимо как:
- `constants.py` строка 20: `25 * 1024 * 1024`
- `document.py` строка 34: `25 * 1024 * 1024` (локальная копия)

При изменении константы в одном файле второй сохраняет старое значение. Реальная проверка в `_validate_docx_archive` использует локальную копию из `document.py`.

#### Целевое изменение в `document.py`

Удалить объявление `MAX_DOCX_ARCHIVE_SIZE_BYTES = 25 * 1024 * 1024` из модульного уровня и добавить импорт:

```python
from constants import (
    MAX_DOCX_ARCHIVE_SIZE_BYTES,
    MAX_DOCX_UNCOMPRESSED_SIZE_BYTES,
    MAX_DOCX_ENTRY_COUNT,
    MAX_DOCX_COMPRESSION_RATIO,
)
```

> Убедиться, что `MAX_DOCX_UNCOMPRESSED_SIZE_BYTES`, `MAX_DOCX_ENTRY_COUNT`, `MAX_DOCX_COMPRESSION_RATIO` также объявлены в `constants.py`.

---

### FIX-05 · `_CLEANUP_THREAD_STARTED` — сброс флага под локом

**Файл:** `app.py`  
**Приоритет:** P0

**Проблема:** Фоновый cleanup-поток сбрасывает `_CLEANUP_THREAD_STARTED = False` без захвата `_CLEANUP_THREAD_LOCK`, тогда как чтение и запись в главном потоке происходят под локом. Логическое TOCTOU.

#### Целевой код

```python
def worker() -> None:
    from restart_store import cleanup_stale_persisted_sources
    try:
        cleanup_stale_persisted_sources(max_age_seconds=PERSISTED_SOURCE_TTL_SECONDS)
    finally:
        with _CLEANUP_THREAD_LOCK:
            global _CLEANUP_THREAD_STARTED
            _CLEANUP_THREAD_STARTED = False
```

---

## 4. Фаза 1 — Корректность данных (P1)

---

### FIX-06 · `preserve_source_paragraph_properties` / `normalize_semantic_output_docx` — диагностика при несоответствии размеров

**Файл:** `document.py`  
**Приоритет:** P1  
**Тест:** `tests/test_document.py`, `tests/test_document_pipeline.py`

#### Проблема

Обе функции используют `zip(source_paragraphs, target_paragraphs)`. Если AI добавила или удалила абзацы, `zip()` молча обрезает до меньшего — форматирование применяется к неверным абзацам без предупреждения.

#### Целевые изменения

В `preserve_source_paragraph_properties`:

```python
if len(source_paragraphs) != len(target_paragraphs):
    from logger import log_event
    import logging
    log_event(
        logging.WARNING,
        "paragraph_count_mismatch_preserve",
        "Число source/target абзацев не совпадает при переносе свойств форматирования; "
        "применение частичное по zip().",
        source_count=len(source_paragraphs),
        target_count=len(target_paragraphs),
    )
```

В `normalize_semantic_output_docx` — аналогично с `event_id="paragraph_count_mismatch_normalize"`.

Логировать перед zip-циклом. Не бросать исключение — частичное применение лучше полного пропуска.

---

### FIX-07 · `extract_scene_graph` — добавить retry, timeout, корректное потребление бюджета

**Файл:** `image_reconstruction.py`  
**Приоритет:** P1  
**Тест:** `tests/test_image_reconstruction.py`

#### Проблема

```python
response = client.responses.create(
    model=model,
    input=[...],
    temperature=0.0,
    # нет timeout, нет retry, нет budget
)
```

Остальной пайплайн использует `call_responses_create_with_retry(timeout=60.0, max_retries=2)`. `extract_scene_graph` блокирует фоновый поток навсегда при сетевой задержке.

Дополнительно: `_generate_reconstructed_candidate` потребляет бюджет **до** вызова, а не после:

```python
_consume_budget(budget, "deterministic_reconstruction.responses.create")  # pre-consume
candidate_bytes, scene_graph = reconstruct_image(...)  # если упадёт — бюджет уже потрачен
```

#### Целевые изменения

**`image_reconstruction.py`, `extract_scene_graph`:**

```python
from image_shared import call_responses_create_with_retry, is_retryable_error

def extract_scene_graph(
    image_bytes: bytes,
    *,
    model: str = DEFAULT_RECONSTRUCTION_MODEL,
    mime_type: str | None = None,
    client=None,
    budget=None,
) -> dict[str, Any]:
    if client is None:
        raise RuntimeError("Scene graph extraction requires an explicit client.")

    prompt_text = _load_scene_graph_prompt()
    data_uri = _image_bytes_to_data_uri(image_bytes, mime_type)

    response = call_responses_create_with_retry(
        client,
        {
            "model": model,
            "input": [
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": prompt_text},
                        {"type": "input_image", "image_url": data_uri},
                    ],
                }
            ],
            "temperature": 0.0,
            "timeout": 60.0,
        },
        max_retries=2,
        retryable_error_predicate=is_retryable_error,
        budget=budget,
    )
    ...
```

**`image_generation.py`, `_generate_reconstructed_candidate`:**

Убрать `_consume_budget(budget, "deterministic_reconstruction.responses.create")` — бюджет теперь потребляется внутри `call_responses_create_with_retry` через `extract_scene_graph`.

Добавить `budget=budget` в вызов `reconstruct_image(...)`.

---

### FIX-08 · `call_responses_create_with_retry` — бюджет не потребляется на неудачных попытках

**Файл:** `image_shared.py`  
**Приоритет:** P1  
**Тест:** `tests/test_image_analysis.py`

#### Проблема

```python
except Exception as exc:
    consume_budget()       # ← потребление при ошибке без реального API-вызова
    if attempt >= max_retries or not retryable_error_predicate(exc):
        raise
    time.sleep(...)
```

При retryable-ошибке (429, 500) бюджет убывает на каждую неудачную попытку. После трёх timeout-ов при бюджете 3 — следующая операция упадёт с `BudgetExceeded` без единого успешного вызова.

#### Целевой код

```python
except Exception as exc:
    should_retry = attempt < max_retries and retryable_error_predicate(exc)
    if not should_retry:
        consume_budget()   # потребить только при финальной ошибке или non-retryable
        raise
    time.sleep(min(2 ** (attempt - 1), max_backoff_seconds))
    # retry: бюджет не тратится до успеха или финального сбоя
else:
    consume_budget()
    return response
```

> **Примечание:** Семантика "один вызов = одна единица бюджета" сохраняется; просто перенести точку потребления на финальный исход попытки.

---

### FIX-09 · `restart_store` — санитизация символов файловой системы в именах файлов

**Файл:** `restart_store.py`  
**Приоритет:** P1  
**Тест:** `tests/test_restart_store.py`

#### Проблема

`source_token = f"{file_name}:{file_size}:{hash}"`. После `replace(":", "_")` в имени файла могут остаться `<`, `>`, `*`, `?`, `\`, `/`, `"` — символы, запрещённые в Windows-путях. На WSL с Windows-хостом `Path.write_bytes()` с такими символами бросит `OSError`.

#### Целевые изменения

```python
import re

def _sanitize_for_filename(value: str) -> str:
    """Заменить символы, запрещённые в именах файлов Windows и Linux."""
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", value)

def _build_persisted_source_path(prefix: str, session_id: str, source_token: str, source_name: str) -> Path:
    safe_session_id = _sanitize_for_filename(session_id)
    safe_token = _sanitize_for_filename(source_token)
    return RUN_DIR / f"{prefix}_{safe_session_id}_{safe_token}{_sanitize_suffix(source_name)}"
```

---

### FIX-10 · `_raise_or_fail_preparation` — корректная проверка пустого `target_text`

**Файл:** `application_flow.py`  
**Приоритет:** P1

#### Проблема

```python
if any(not str(job["target_text"]).strip() for job in prepared_document.jobs):
```

`str(None)` = `"None"`, которое не пустое → job с `target_text=None` проходит проверку и модель получает буквальный текст `"None"`.

#### Целевой код

```python
if any(not str(job.get("target_text") or "").strip() for job in prepared_document.jobs):
    ...
```

---

## 5. Фаза 2 — Архитектурная надёжность (P2)

---

### FIX-11 · Zip-slip protection в `_validate_docx_archive`

**Файл:** `document.py`  
**Приоритет:** P2  
**Тест:** `tests/test_document.py`

#### Проблема

ZIP-архив может содержать записи с путями `../../../etc/passwd` или `/etc/passwd`. `_validate_docx_archive` не проверяет формат имён записей. Хотя `Document(BytesIO(...))` сейчас не распаковывает на диск, добавление любой файловой операции в будущем создаст path traversal.

#### Целевые изменения

Добавить в конец блока проверок в `_validate_docx_archive`:

```python
for entry in entries:
    entry_name = entry.filename
    # Запретить абсолютные пути и traversal-компоненты
    parts = entry_name.replace("\\", "/").split("/")
    if any(part == ".." for part in parts):
        raise RuntimeError(
            "DOCX-архив содержит подозрительные пути и отклонён из соображений безопасности."
        )
    if entry_name.startswith("/"):
        raise RuntimeError(
            "DOCX-архив содержит абсолютные пути и отклонён из соображений безопасности."
        )
```

---

### FIX-12 · Удалить мёртвый код в `document_pipeline.py`

**Файл:** `document_pipeline.py`  
**Приоритет:** P2

#### Проблема

После основного цикла обработки блоков присутствует проверка:

```python
if len(processed_chunks) != job_count:
    # critical error path …
    return "failed"
```

Этот код **недостижим** при нормальном завершении: каждая итерация цикла либо добавляет ровно один chunk, либо возвращает `"failed"` / `"stopped"`. Создаёт ложное ощущение дополнительной защиты и запутывает читателя.

#### Целевое действие

Удалить блок `if len(processed_chunks) != job_count:` целиком вместе с вызовами `emit_*` и `return "failed"` внутри него.

---

### FIX-13 · Типизировать поля `ProcessingService`

**Файл:** `processing_service.py`  
**Приоритет:** P2

#### Проблема

```python
@dataclass
class ProcessingService:
    get_client_fn: object
    load_system_prompt_fn: object
    # ... 28 полей с типом object
```

Protocol-классы уже определены в `document_pipeline.py` (`ClientFactory`, `SystemPromptLoader`, `MarkdownGenerator`, и т.д.) но не используются в `ProcessingService`.

#### Целевые изменения

```python
from document_pipeline import (
    ClientFactory,
    SystemPromptLoader,
    MarkdownGenerator,
    MarkdownToDocxConverter,
    PlaceholderInspector,
    ParagraphPropertiesPreserver,
    SemanticDocxNormalizer,
    ImageReinserter,
    EventLogger,
    ErrorPresenter,
    StateEmitter,
    FinalizeEmitter,
    ActivityEmitter,
    LogEmitter,
    StatusEmitter,
    StopPredicate,
    FilenameResolver,
)

@dataclass
class ProcessingService:
    get_client_fn: ClientFactory
    load_system_prompt_fn: SystemPromptLoader
    ensure_pandoc_available_fn: Callable[[], None]
    generate_markdown_block_fn: MarkdownGenerator
    convert_markdown_to_docx_bytes_fn: MarkdownToDocxConverter
    # ... остальные поля с конкретными Protocol-типами
```

> Добавлять постепенно, по одному полю за PR, чтобы не сломать mypy и тесты.

---

### FIX-14 · `generate_markdown_block` — добавить `max_output_tokens`

**Файл:** `generation.py`  
**Приоритет:** P2

#### Проблема

Вызов `client.responses.create(model=model, input=payload)` не задаёт `max_output_tokens`. Модель может генерировать до своего контекстного лимита (128k+ токенов для GPT-5). Для больших блоков это ведёт к избыточным расходам API и потенциальным таймаутам.

#### Целевые изменения

```python
# В generate_markdown_block, перед вызовом API:
estimated_output_tokens = max(len(target_text) // 3 * 4, 512)   # ≈ 4/3 от input chars, min 512
capped_output_tokens = min(estimated_output_tokens, 16384)

response = client.responses.create(
    model=model,
    input=payload,
    max_output_tokens=capped_output_tokens,
)
```

> Если Responses API не поддерживает `max_output_tokens` — обернуть в `try/except TypeError` аналогично механизму удаления `timeout` в `call_responses_create_with_retry`.

---

## 6. Фаза 3 — Производительность и наблюдаемость (P3)

---

### FIX-15 · `_build_variant_table_element` — убрать временный `Document()`

**Файл:** `document.py`  
**Приоритет:** P3

#### Проблема

```python
temp_document = Document()    # создаёт полный python-docx Document со всеми стилями
temp_table = temp_document.add_table(rows=1, cols=len(insertions))
table = Table(deepcopy(temp_table._element), paragraph._parent)
```

При `compare_all` с 10 изображениями — 10 временных Document-объектов. Каждый объект загружает шаблон стилей в память.

#### Целевые изменения

Создавать `tbl` XML-элемент напрямую через `OxmlElement`, без `Document()`:

```python
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

def _build_variant_table_element(paragraph, asset: ImageAsset):
    insertions = resolve_image_insertions(asset)
    col_count = len(insertions)

    tbl = OxmlElement("w:tbl")
    tblPr = OxmlElement("w:tblPr")
    tbl.append(tblPr)
    tblGrid = OxmlElement("w:tblGrid")
    for _ in range(col_count):
        gridCol = OxmlElement("w:gridCol")
        tblGrid.append(gridCol)
    tbl.append(tblGrid)

    tr = OxmlElement("w:tr")
    tbl.append(tr)
    add_picture_kwargs = _build_picture_size_kwargs(asset)
    for label, image_bytes in insertions:
        tc = OxmlElement("w:tc")
        p = OxmlElement("w:p")
        r = OxmlElement("w:r")
        Run(r, paragraph).add_picture(BytesIO(image_bytes), **add_picture_kwargs)
        if label:
            _set_picture_description(r, label)
        p.append(r)
        tc.append(p)
        tr.append(tc)

    table = Table(tbl, paragraph._parent)
    _configure_variant_table_layout(table)
    return tbl
```

---

### FIX-16 · Логировать hit/miss кэша preparation

**Файл:** `preparation.py`  
**Приоритет:** P3

#### Целевые изменения

В `prepare_document_for_processing`, в ветке кэш-хита:

```python
if cached is not None:
    log_event(
        logging.DEBUG,
        "preparation_cache_hit",
        "Использован кэш подготовки документа.",
        prepared_source_key=prepared_source_key,
        cache_level="session" if ...,
    )
    return cached
```

В ветке промаха и успешной подготовки добавить `"preparation_cache_miss"`.

---

## 7. Критерии завершения

Каждая фаза считается закрытой при выполнении всех пунктов:

### Фаза 0 (P0)

- [ ] `parse_json_object` корректно обрабатывает `` ` `` в JSON-содержимом.
- [ ] Новые тесты `test_parse_json_object_with_backtick_in_content` и `test_parse_json_object_fence_without_newline` проходят.
- [ ] `_replace_xml_element_with_sequence` с пустым списком — noop, тест проходит.
- [ ] `.streamlit/config.toml` содержит `maxUploadSize = 25`.
- [ ] `document.py` не содержит локального объявления `MAX_DOCX_ARCHIVE_SIZE_BYTES`.
- [ ] `_CLEANUP_THREAD_STARTED = False` выполняется под `_CLEANUP_THREAD_LOCK`.
- [ ] Все существующие тесты проходят: `bash scripts/test.sh tests/ -q`.

### Фаза 1 (P1)

- [ ] В логах появляется `WARNING paragraph_count_mismatch_*` при несоответствии числа абзацев.
- [ ] `extract_scene_graph` использует `call_responses_create_with_retry` с `timeout=60.0`.
- [ ] Бюджет не потребляется на retryable-ошибках (unit-тест с mock).
- [ ] `restart_store` корректно обрабатывает имена файлов с `<>:"/\|?*`.
- [ ] Проверка пустого `target_text` работает для `None`.

### Фаза 2 (P2)

- [ ] `_validate_docx_archive` отклоняет ZIP с `../` в именах записей.
- [ ] Мёртвый код `len(processed_chunks) != job_count` удалён, тест-coverage не ухудшился.
- [ ] `ProcessingService` использует Protocol-типы для ≥10 полей.
- [ ] `generate_markdown_block` передаёт `max_output_tokens`.

### Фаза 3 (P3)

- [ ] `_build_variant_table_element` не создаёт временный `Document()`.
- [ ] В логах присутствуют события `preparation_cache_hit` / `preparation_cache_miss`.
- [ ] Полный прогон тестов: `bash scripts/test.sh tests/ -q`.

---

## 8. Полный реестр проблем

| ID | Файл | Строки | Категория | Критичность | Фаза | Описание |
|---|---|---|---|---|---|---|
| BUG-01 | `image_shared.py` | ≈48-56 | Corruption | P0 | Фаза 0 | `parse_json_object`: `strip(backtick)` обрезает JSON с `` ` `` в значениях |
| BUG-02 | `document.py` | `_replace_xml_element_with_sequence` | Data loss | P0 | Фаза 0 | Удаляет XML-элемент при пустом списке замен |
| SEC-01 | `document.py`, `config.toml` | — | Security/DoS | P0 | Фаза 0 | Файл читается в память до проверки размера; Streamlit не ограничивает upload |
| DUP-01 | `document.py`, `constants.py` | 34, 20 | Maintenance | P0 | Фаза 0 | `MAX_DOCX_ARCHIVE_SIZE_BYTES` объявлена дважды |
| RACE-01 | `app.py` | ≈66-79 | Race condition | P0 | Фаза 0 | `_CLEANUP_THREAD_STARTED = False` без лока в фоновом потоке |
| BUG-03 | `document.py` | 183, 203 | Silent mismatch | P1 | Фаза 1 | `zip()` без диагностики при несоответствии числа абзацев |
| BUG-06 | `image_reconstruction.py` | `extract_scene_graph` | Blocking/Budget | P1 | Фаза 1 | Нет retry/timeout; pre-consume бюджета до вызова |
| BUG-05 | `image_shared.py` | ≈103 | Budget accounting | P1 | Фаза 1 | Бюджет потребляется на неудачных retryable-попытках |
| BUG-09 | `restart_store.py` | `_build_persisted_source_path` | OSError | P1 | Фаза 1 | Небезопасные символы файловой системы в именах файлов |
| BUG-10 | `application_flow.py` | ≈186 | Null bypass | P1 | Фаза 1 | `str(None)` = `"None"` проходит проверку пустого блока |
| SEC-02 | `document.py` | `_validate_docx_archive` | Path traversal | P2 | Фаза 2 | Zip-slip: имена записей с `../` не проверяются |
| DEAD-01 | `document_pipeline.py` | после основного цикла | Dead code | P2 | Фаза 2 | `len(processed_chunks) != job_count` недостижим |
| ARCH-01 | `processing_service.py` | все поля | Type safety | P2 | Фаза 2 | 30 полей типа `object` вместо Protocol |
| BUG-12 | `generation.py` | `generate_markdown_block` | Resource | P2 | Фаза 2 | Нет `max_output_tokens` — возможны таймауты и переплаты |
| PERF-01 | `document.py` | `_build_variant_table_element` | Performance | P3 | Фаза 3 | Временный `Document()` на каждое изображение в compare_all |
| OBS-01 | `preparation.py` | `prepare_document_for_processing` | Observability | P3 | Фаза 3 | Нет логирования hit/miss кэша подготовки |
| ARCH-03 | `preparation.py` | `_shared_preparation_cache` | Multi-user | INFO | — | Process-wide кэш содержит байты документов; при multi-user deploy требует изоляции |
| ARCH-04 | `image_generation.py` | `_generate_semantic_candidate` | Performance | INFO | — | До 4 последовательных fallback AI-вызовов на одно изображение без уведомления |
| API-01 | `generation.py` | `generate_markdown_block` | Compatibility | INFO | — | Использует Responses API (beta), а не стандартный Chat Completions |
