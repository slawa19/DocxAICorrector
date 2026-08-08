# Историческая спецификация декомпозиции app.py

> Статус: archived historical spec. Этот документ фиксирует первую волну декомпозиции `app.py`. Текущее состояние репозитория уже шире исходного плана и включает дополнительные модули вроде `application_flow.py`, `preparation.py`, `processing_runtime.py`, `processing_service.py`, `document_pipeline.py` и `image_*`. Для актуальной карты модулей используйте `README.md`, а для архивной навигации `docs/ARCHIVE_INDEX.md`.

## Контекст

`app.py` вырос до ~1310 строк и совмещает несколько независимых зон ответственности:
константы, логирование, конфигурация, работа с документом, AI-генерация, управление
состоянием Streamlit, UI-компоненты и основная оркестрация (`main`).

Цель декомпозиции — разбить файл на модули с однозначными зонами ответственности,
не меняя поведение приложения и не добавляя новых абстракций.

---

## Целевая структура

```
DocxAICorrector/
├── app.py              ← только main() + st.set_page_config (≈80 строк)
├── constants.py        ← пути и DEFAULT-значения
├── models.py           ← ParagraphUnit, DocumentBlock
├── logger.py           ← инфраструктура логирования
├── config.py           ← загрузка конфигурации, клиент OpenAI, Pandoc
├── document.py         ← разбор DOCX, сборка смысловых блоков
├── generation.py       ← вызов OpenAI API, сборка DOCX через Pandoc
├── state.py            ← инициализация и управление session_state
├── ui.py               ← все Streamlit-компоненты (рендеринг)
├── .streamlit/
│   └── config.toml     ← тема Streamlit (primaryColor и др.)
└── config.toml         ← пользовательский конфиг приложения
```

---

## Описание модулей

### `constants.py`
Зависимости: нет (только `pathlib`).

Экспортирует:
- `BASE_DIR`, `PROMPTS_DIR`, `CONFIG_PATH`, `SYSTEM_PROMPT_PATH`, `RUN_DIR`, `APP_LOG_PATH`
- `DEFAULT_MODEL`, `DEFAULT_MODEL_OPTIONS`, `DEFAULT_CHUNK_SIZE`, `DEFAULT_MAX_RETRIES`

### `models.py`
Зависимости: нет (только `dataclasses`).

Экспортирует:
- `ParagraphUnit(text: str, role: str)`
- `DocumentBlock(paragraphs: list[ParagraphUnit])` — свойство `.text`

### `logger.py`
Зависимости: `constants`.

Экспортирует:
- `LOGGER` — настроенный `RotatingFileHandler` → `.run/app.log`
- `setup_logger()`, `make_event_id()`, `format_elapsed()`
- `sanitize_log_context()`, `log_event()`, `log_exception()`
- `extract_exception_message()`, `format_user_error()`
- `present_error()`, `fail_critical()`

### `config.py`
Зависимости: `constants`.
Внешние: `tomllib`, `openai`, `dotenv`.

Экспортирует:
- `load_app_config() -> dict`
- `load_system_prompt() -> str`
- `get_client() -> OpenAI`
- `parse_int_env()`, `parse_csv_env()` (вспомогательные)

### `document.py`
Зависимости: `models`.
Внешние: `re`, `docx`.

Экспортирует:
- `classify_paragraph_role(text, style_name) -> str`
- `extract_paragraph_units_from_docx(uploaded_file) -> list[ParagraphUnit]`
- `build_document_text(paragraphs) -> str`
- `build_semantic_blocks(paragraphs, max_chars) -> list[DocumentBlock]`
- `build_context_excerpt(blocks, block_index, limit_chars, *, reverse) -> str`
- `build_editing_jobs(blocks, max_chars) -> list[dict]`

### `generation.py`
Зависимости: нет (только stdlib + внешние).
Внешние: `openai`, `pypandoc`, `tempfile`, `pathlib`.

Экспортирует:
- `ensure_pandoc_available()`
- `normalize_model_output(text) -> str`
- `is_retryable_error(exc) -> bool`
- `generate_markdown_block(client, model, system_prompt, target_text, context_before, context_after, max_retries) -> str`
- `convert_markdown_to_docx_bytes(markdown_text) -> bytes`
- `build_output_filename(filename) -> str`
- `build_markdown_filename(filename) -> str`

### `state.py`
Зависимости: `constants` (для `APP_LOG_PATH` в `last_log_hint`).
Внешние: `streamlit`, `time`, `datetime`.

Экспортирует:
- `init_session_state()`
- `reset_run_state()`
- `push_activity(message)`
- `set_processing_status(*, stage, detail, ...)`
- `finalize_processing_status(stage, detail, progress)`
- `append_log(status, block_index, block_count, target_chars, context_chars, details)`

### `ui.py`
Зависимости: `logger` (для `format_elapsed`), `generation` (для `build_output_filename`, `build_markdown_filename`).
Внешние: `streamlit`, `html`, `time`.

Экспортирует:
- `inject_ui_styles()`
- `render_live_status(target=None)`
- `render_run_log(target=None)`
- `render_sidebar(config) -> tuple[str, int, int]`
- `render_markdown_preview(target=None, *, title)`
- `render_result(docx_bytes, markdown_text, original_filename)`
- `render_partial_result()`

### `app.py` (после декомпозиции)
Зависимости: все модули выше.

Содержит только:
- `st.set_page_config(...)` на уровне модуля
- `main()` — оркестрация (загрузка конфига, чтение файла, цикл обработки, рендеринг)
- `if __name__ == "__main__": main()`

---

## Граф зависимостей

```
constants ──────────────────────────────────────────┐
models ──────────────────────────────────────────┐  │
                                                 │  │
logger ◄── constants                             │  │
config ◄── constants                             │  │
document ◄── models                              │  │
generation (нет зависимостей от проекта)         │  │
state ◄── constants                              │  │
ui ◄── logger, generation                        │  │
                                                 │  │
app ◄── все                                      ▼  ▼
```

Циклических зависимостей нет.

---

## Что НЕ меняется

- Поведение приложения: ни один публичный интерфейс не изменяется
- `config.toml`, `.env`, `prompts/system_prompt.txt` — без изменений
- `st.set_page_config` остаётся первым вызовом в `app.py` (требование Streamlit)
- логирование по-прежнему централизовано в `logger.py`, но в текущей реализации используется lazy initialization вместо обязательного side effect при import

---

## Порядок реализации

1. `constants.py`
2. `models.py`
3. `logger.py`
4. `config.py`
5. `document.py`
6. `generation.py`
7. `state.py`
8. `ui.py`
9. `app.py` — перезаписать, оставив только `main()`
