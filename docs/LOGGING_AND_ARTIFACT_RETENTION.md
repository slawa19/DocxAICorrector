# Logging and Artifact Retention Contract

Статус: каноническая документация.
Последняя ревизия: 2026-04-19.
Связанные документы: `README.md` (раздел «Логи»), `docs/AI_AGENT_DEVELOPMENT_RULES.md`, `docs/archive/specs/LOGGING_AND_DISK_RETENTION_SPEC_2026-03-27.md` (исходная спецификация).

Назначение документа: зафиксировать единый источник правды по логированию и retention runtime-артефактов, чтобы ИИ-агент при добавлении новых фич:

- не использовал сторонние логгеры вместо централизованного,
- всегда добавлял log-event для значимых runtime-состояний,
- не создавал новые artifact-директории без TTL/count-cap,
- не вводил параллельные policy-значения, разбросанные по модулям.

---

## 1. Logging architecture

### 1.1 Owner

Централизованный логгер живёт в `logger.py` и является единственным разрешённым каналом application-level логирования для production-кода. Использовать `logging.getLogger(__name__)` напрямую в production-модулях запрещено — только через `get_logger()`/`log_event()`/`log_exception()`.

- Logger name: `docxaicorrector`.
- Destination: `.run/app.log` через `_WSLSafeRotatingFileHandler` (max `1_000_000` байт, `backupCount=3`, UTF-8).
- Формат записи: `"%(asctime)s | %(levelname)s | %(message)s"` — где `message` сериализуется как JSON-payload вида
  `{"event_id": ..., "event": ..., "message": ..., "context": {...}}`.
- Уровень: читается один раз из env-переменной `DOCX_AI_LOG_LEVEL` (DEBUG/INFO/WARNING/ERROR/CRITICAL, case-insensitive). Неизвестное значение даёт fallback `INFO` и одну WARNING-запись на старте.

### 1.2 Public API

| Функция | Назначение | Возвращает |
|---------|-----------|------------|
| `get_logger()` | Ленивая инициализация `Logger`. | `logging.Logger` |
| `log_event(level, event, message, **context)` | Основной способ записи runtime-события. JSON-сериализует `context` через `sanitize_log_context`. | `event_id` строкой |
| `log_exception(event, exc, message, **context)` | Запись падения с `error_type`/`error_message`/`status_code`. Использует `logger.exception`, что добавляет traceback. | `event_id` |
| `present_error(event, exc, message, **context)` | Логирует через `log_exception` и возвращает человекочитаемую строку через `format_user_error`. Используется для `last_error` в UI. | user-facing текст |
| `fail_critical(event, message, **context)` | Пишет CRITICAL-event и поднимает `RuntimeError("… [log: evt-…]")`. | `NoReturn` |
| `make_event_id(prefix)` | Только для редких случаев, когда нужно получить `event_id` без записи (например, передать во внешнюю систему). | `evt-<ms>` строка |
| `format_elapsed(seconds)` | Форматирование длительностей для UI и логов. | `HH:MM:SS` / `MM:SS` |

`context` санитизируется `sanitize_log_context()`. Path, dict, list/tuple/set и скаляры проходят как есть, всё остальное приводится к `str()`. Не кладите в контекст объекты с неконтролируемым `__repr__` (DOCX, `BytesIO`, numpy-массивы) — приводите к compact JSON-safe виду самостоятельно.

### 1.3 Event-id в UI

Все user-facing ошибки, построенные через `present_error(...)`, содержат фрагмент `[log: evt-…]`. Этот `event_id` позволяет найти запись в `.run/app.log` по substring-поиску. При ручном формировании user-facing ошибки из уже залогированного события всегда используйте возвращаемый `event_id`, чтобы пользовательское сообщение было линкуемо к записи в логе.

### 1.4 Event-callback контракт

Функции нижнего слоя, которые не импортируют `logger` напрямую (`application_flow.py`, `state.py`, `image_pipeline.py`, `processing_service.py`, `real_document_validation_*.py`), принимают callable `log_event_fn: (level, event_id, message, **context) -> None`. Production-call site передаёт `log_event` из `logger.py`. Тесты передают lambda-stub. Это единственный разрешённый способ инверсии зависимости от логгера — новые модули низкого слоя должны следовать тому же паттерну.

### 1.5 Когда НЕ логировать

- Не пишите `log_event` на каждую итерацию UI fragment'а (render-цикл Streamlit). Для UI-видимых активностей используйте `push_activity`/ append-log events в runtime state.
- Не логируйте полезную нагрузку модели целиком (prompts, model responses, markdown блоков полностью). Допустимы truncated preview (≤ 120 символов), counts и hash.
- Не логируйте секреты: ключи, bearer-токены, полные URL с API-key, email-идентификаторы пользователей.

---

## 2. Level policy

| Уровень | Когда использовать | Примеры событий |
|---------|-------------------|-----------------|
| DEBUG | Высокочастотные per-item события, детализированные payload'ы | `block_started`, `block_plan_detail`, `image_candidate_generated` |
| INFO | Run boundaries, переходы между стадиями, успешные терминальные события | `processing_started`, `processing_completed`, `block_plan_summary`, `preparation_cache_hit`, `structure_recognition_debug_artifact_saved` |
| WARNING | Recoverable деградации, fallback-ветки, retry после transient-ошибки | `structure_recognition_fallback`, `prompt_quality_warning`, `markdown_empty_response_recovery_started`, `semantic_image_edit_retry_after_transient_error` |
| ERROR | Terminal failure одного элемента в общем плане (но не всего run'а) | `block_failed`, `docx_build_failed`, `image_processing_failed`, `image_validation_failed` |
| CRITICAL | Системный отказ runtime-контракта, ведущий к прерыванию (`fail_critical`) | ассерт-подобные нарушения инвариантов |

Правила, следующие из `LOGGING_AND_DISK_RETENTION_SPEC_2026-03-27`:

1. `block_started` остаётся на DEBUG. На INFO должны быть только `processing_started`, `block_plan_summary`, `processing_completed` и terminal-переходы.
2. `block_plan_summary` (INFO) содержит только агрегаты и первые N чисел. Полный список блоков идёт отдельным `block_plan_detail` на DEBUG.
3. Image retry/adaptation цепочки: detail-per-attempt → DEBUG; user-видимая деградация → WARNING; exhaustion → ERROR.

Если новое событие должно помочь только при активной отладке — используйте DEBUG. Если событие должно быть видно всегда при разборе продового failure — WARNING/ERROR.

---

## 3. Event taxonomy (current catalog)

Полный актуальный список events можно перегенерировать:

```bash
bash -c "cd /mnt/d/www/projects/2025/DocxAICorrector && python3 scripts/_list_log_events.py"
```

Скрипт сканирует ключевые production-модули и печатает `event\tfile`. Используйте его как инструмент аудита перед добавлением новых имён, чтобы избежать дубликатов.

На момент ревизии документа зафиксированы следующие группы:

### 3.1 App bootstrap

- `app_start` — `app.py`, INFO.
- `config_load_failed`, `document_read_failed` — `app.py`, через `present_error`/`fail_critical`.
- `legacy_model_config_key_detected`, `legacy_model_config_source_used`, `model_registry_resolved` — `config.py`, INFO/WARNING при устаревших ключах.

### 3.2 Preparation

- `preparation_cache_hit`, `preparation_cache_miss` — `preparation.py`, INFO.
- `structure_recognition_debug_artifact_saved`, `structure_recognition_fallback`, `structure_validation_debug_artifact_saved`, `structure_processing_outcome` — `preparation.py`.
- `restart_source_store_failed` — `processing_runtime.py`.

### 3.3 Document pipeline (main loop)

- `processing_started` (INFO, run boundary).
- `block_plan_summary` (INFO) + `block_plan_detail` (DEBUG).
- `block_started` (DEBUG), `block_completed`, `block_failed`, `block_rejected`.
- `empty_processed_block`, `structurally_insufficient_processed_block`, `processed_block_count_mismatch`.
- `block_marker_registry_built`, `block_marker_registry_failed`, `marker_diagnostics_artifact_created`.
- `image_placeholder_integrity_failed`, `image_placeholder_mismatch`, `image_processing_failed`.
- `docx_build_failed`, `empty_docx_bytes`.
- `formatting_diagnostics_artifacts_detected`.
- `invalid_processing_job`, `invalid_processing_plan`, `processing_init_failed`.
- `processing_completed` (INFO, run boundary).

### 3.4 Generation

- `context_leakage_persisted`, `image_only_target_passthrough`.
- `markdown_empty_response_recovery_started`, `markdown_incomplete_response_source_fallback`.
- `model_empty_response_shape`, `prompt_quality_warning`.

### 3.5 Image pipeline

- `image_analysis_vision_fallback_after_error`.
- Image generation attempts: `semantic_image_edit_completed|fallback_to_structured_generate|retry_after_transient_error|retry_with_fallback_size|retry_with_shorter_prompt|retry_without_optional_param`.
- Structured image generation attempts: `structured_image_generate_completed|retry_after_transient_error|retry_with_fallback_size|retry_with_shorter_prompt|retry_without_optional_param`.
- Layout retries: `structured_layout_retry_after_transient_error|without_optional_param`.
- Creative/semantic: `creative_semantic_generate_completed|fallback_to_direct_edit`, `semantic_image_edit_completed`.
- `image_candidate_generated`, `safe_image_enhancement_skipped`.
- Reconstruction: `deterministic_reconstruction_succeeded|failed`, `scene_graph_extracted`, `image_reconstruction_completed`, `structured_edit_fallback_to_generate`, `structured_generate_fallback_to_reconstruction`.
- Validation: `image_validation_started|completed|failed`, `image_vision_validation_skipped_after_failure`.
- Reinsertion: `image_reinsertion_placeholder_unhandled`.

### 3.6 Runtime infrastructure

- `state_event_unknown_keys` — `processing_runtime.py`, WARNING: неизвестный ключ в `SetStateEvent`.
- `artifact_pruned` — `runtime_artifact_retention.py`, DEBUG: после фактического удаления одного или более файлов. Context: `{dir, removed_count, max_age_seconds, max_count}`.

---

## 4. Rules for adding new log events (AI agent checklist)

При любой новой production-ветке с netrivial runtime-эффектом ИИ-агент обязан:

1. Проверить, что для события уже нет event-имени в каталоге из §3 (или через `scripts/_list_log_events.py`). Если подходящее имя уже есть — переиспользовать.
2. Имя события — `snake_case`, глобально уникальное, читается как «что произошло»: `subject_action[_qualifier]`. Примеры: `block_rejected`, `image_validation_failed`, `structure_recognition_fallback`. Не использовать имена вида `debug1`, `step2`, `error`.
3. Уровень выбирается по §2. При сомнении — WARNING для деградации, DEBUG для детализации.
4. Context keys должны быть стабильными и reusable:
   - `filename`, `model`, `block_index`, `block_count`, `target_chars`, `context_chars`, `job_kind` — для document pipeline;
   - `image_id`, `image_mode`, `attempt_index`, `error_type`, `status_code` — для image pipeline;
   - `cache_key`, `source_hash`, `profile`, `mode` — для preparation/structure;
   - `elapsed_ms`, `bytes`, `count` — для метрик.
   Не добавляйте новый context-key, если уже есть семантически идентичный (например, не плодите `file_name`/`filename`/`source_file` для одного и того же значения).
5. Не логируйте полное тело prompt или model response. Для диагностики используйте:
   - preview (≤ 120 символов),
   - длину (`len_chars`, `len_bytes`),
   - short hash (`sha1[:12]`).
6. Если событие сигнализирует о user-видимой ошибке — дополнительно используйте `present_error(event, exc, ...)` и положите user-facing строку в `last_error`. Не вызывайте `log_exception` + собственный `format_user_error` параллельно — `present_error` делает оба шага атомарно.
7. Для критических нарушений runtime-инварианта — только `fail_critical(event, message, ...)`. Не поднимайте `RuntimeError` с самостоятельным текстом, если это инвариантный отказ.
8. Для низких слоёв без прямого импорта `logger` — принимайте `log_event_fn` параметром и пробрасывайте production-значение через constructor/args, тест передаст stub.
9. Если добавляется новая retry-ветка — обязательно отдельный event на каждую форму retry (transient, fallback-size, shorter-prompt, remove-optional-param), а не один generic `retry`. Это уже работающий паттерн в `image_generation.py`.
10. Если появляется новый run boundary (start/complete), он идёт на INFO вне зависимости от `DOCX_AI_LOG_LEVEL`.

Антипаттерны:

- `logger = logging.getLogger(__name__)` в новом production-модуле.
- `print(...)` для диагностики.
- Логирование на каждой итерации render-цикла Streamlit.
- Смешение `log_event` и ad-hoc `logger.info(json.dumps(...))` — использовать только `log_event`, он уже делает JSON-wrap.
- Пропуск `log_event` в новой fallback-ветке. Каждая user-видимая деградация требует WARNING.
- Сбор "все ключи сразу" в context — держите payload компактным.

---

## 5. Runtime artifact retention

`.run/` — production-like local runtime area. `tests/artifacts/...` — validation/dev workflow, не очищается runtime-механиками.

### 5.1 Канонические retention-механики (реализовано)

| Артефакт | Политика | Владелец |
|----------|---------|----------|
| `.run/app.log` | `RotatingFileHandler`, maxBytes=1_000_000, backupCount=3 | `logger._WSLSafeRotatingFileHandler` |
| `.run/app.ready` | Throttle window = 15s (не переписывается чаще на render-цикл) | `runtime_artifacts.AppReadyMarkerWriter` |
| `.run/formatting_diagnostics/*.json` | TTL 7 дней, max 100 файлов, pruning при каждой записи | `formatting_diagnostics_retention.prune_formatting_diagnostics()` |
| `.run/paragraph_boundary_reports/*.json` | TTL 7 дней, max 300 файлов, pruning при каждой записи | `document._write_paragraph_boundary_report_artifact()` → `runtime_artifact_retention.prune_artifact_dir()` |
| `.run/relation_normalization_reports/*.json` | TTL 7 дней, max 300 файлов, pruning при каждой записи | `document._write_relation_normalization_report_artifact()` → `prune_artifact_dir()` |
| `.run/paragraph_boundary_ai_review/*.json` | TTL 14 дней, max 200 файлов, pruning при каждой записи | `document._write_paragraph_boundary_ai_review_artifact()` → `prune_artifact_dir()` |
| `.run/structure_maps/*.json` | TTL 30 дней, max 200 файлов, pruning при каждой записи | `preparation._write_structure_map_debug_artifact()` → `prune_artifact_dir()` |
| `.run/structure_validation/*.json` | TTL 30 дней, max 200 файлов, pruning при каждой записи | `structure_validation.write_structure_validation_debug_artifact()` → `prune_artifact_dir()` |
| `.run/restart_*`, `.run/completed_*` | TTL 12 часов, cleanup при старте приложения | `restart_store.cleanup_stale_persisted_sources`, вызов из `app._schedule_stale_persisted_sources_cleanup` |
| `.run/project.log` | Size-rollover на PowerShell-стороне (`Invoke-ProjectLogRollover`), backupCount=5, порог `256 KiB` | `scripts/_shared.ps1` |
| `.run/streamlit.log` | Size-rollover в WSL control-скрипте, backupCount=5, порог `256 KiB`, check каждые 30s | `scripts/project-control-wsl.sh :: rotate_streamlit_log_if_needed` |
| stale ad-hoc root файлы (`full_pytest_*.txt`, `wrapper-*.{out,exit}`, `min*.ps1`, `shared-fragment.ps1`, …) | Ручная очистка whitelisted patterns старше `--min-age-days` (по умолчанию 14) | `scripts/clean-stale-run-artifacts.sh` (`--apply` чтобы выполнить) |

Все эти механики трогают строго свои файлы и не ходят в `tests/artifacts/...`.

Политики per-family зафиксированы как константы в `runtime_artifact_retention.py` — это **единственный source of truth** для TTL/count. Writers импортируют оттуда нужную пару значений и вызывают `prune_artifact_dir(target_dir=..., max_age_seconds=..., max_count=...)` сразу после записи нового файла. Pruner является synchronous, filesystem-only, no-op для отсутствующей директории.

### 5.2 Поведение pruner'а

- Никогда не ходит выше `.run/<dir>/`.
- Не трогает subdirectories — только файлы matching `glob` (по умолчанию `*.json`).
- Не трогает файлы, принадлежащие текущему процессу (PID-файлы, `app.ready`, текущий `app.log`) — они находятся в корне `.run/`, а pruner вызывается только для artifact-поддиректорий.
- No-op если директория не существует или не содержит matching файлов.
- На каждом фактическом удалении (если было хоть одно) эмитит DEBUG-event `artifact_pruned` с контекстом `{dir, removed_count, max_age_seconds, max_count}`. Writers могут отключить логирование через `emit_log=False`, если артефакт-путь уже освещён событием более высокого уровня.
- Сначала отбрасываются файлы старше `max_age_seconds`; затем, если превышен `max_count`, удаляются самые старые по mtime (tiebreaker — имя файла). Это делает pruning детерминистичным.

### 5.3 Опциональный `.run`-guardrail (пока не реализовано)

`DOCX_AI_RUN_DIR_MAX_MB` / `DOCX_AI_RUN_DIR_MAX_FILES` как последний защитный барьер — по спецификации опциональны и выключены по умолчанию. Вводить только если per-family policy в §5.1 окажется недостаточной. Детали и приоритет удаления — §P2.1 исходной спецификации `LOGGING_AND_DISK_RETENTION_SPEC_2026-03-27.md`.

### 5.4 Правила для ИИ-агента по новым артефактам

Если новая фича создаёт новый тип файлов в `.run/`:

1. Использовать поддиректорию `.run/<family>/`, не сорить в корень `.run/`.
2. Имя файла — с timestamp или hash, чтобы быть append-safe.
3. Добавить per-family константы `<FAMILY>_MAX_AGE_SECONDS` и `<FAMILY>_MAX_COUNT` в `runtime_artifact_retention.py` (единый source of truth для политик).
4. Сразу после записи файла вызвать `prune_artifact_dir(target_dir=..., max_age_seconds=..., max_count=...)` с этими константами.
5. Зафиксировать policy в этом документе (§5.1) в виде строки таблицы.
6. Добавить unit-тест на retention (pruning по age, по count, preservation of newest). Шаблон тестов — `tests/test_runtime_artifact_retention.py`.
7. Не трогать `tests/artifacts/...` из runtime-кода. Runtime cleanup действует только на `.run/`.
8. Если артефакт-семья генерируется только тест-сценариями, а не production-путём, добавлять её в `scripts/clean-stale-run-artifacts.sh` whitelisted patterns, а не в runtime pruner.

---

## 6. Verification / диагностика

### 6.1 Ad-hoc inspection

- Просмотр текущих событий:
  `wsl.exe -d Debian bash -c "tail -n 200 .run/app.log | sed 's/.*INFO | //'"`.
- Поиск по `event_id` из UI-сообщения:
  `wsl.exe -d Debian bash -c "grep 'evt-1776…' .run/app.log*"`.
- Временная отладка на DEBUG:
  установить в `.env` `DOCX_AI_LOG_LEVEL=DEBUG`, перезапустить приложение, после диагностики вернуть на `INFO`.
- Список всех событий, используемых в коде: `python3 scripts/_list_log_events.py`.

### 6.2 Тесты

- `tests/test_logger.py` — парсинг `DOCX_AI_LOG_LEVEL`, fallback, `log_event`/`log_exception`/`present_error`/`fail_critical` контракты.
- `tests/test_formatting_diagnostics_retention.py` — retention по age/count.
- `tests/test_app.py::test_mark_app_ready_uses_shared_throttled_writer` — throttle для `app.ready`.
- Для любого нового artifact family'и обязательно unit-тест на retention.

### 6.3 Не путать

- `.run/app.log` — production logger. Используется `log_event`/`log_exception`.
- `.run/project.log` — shell control-plane (start/stop/status), PowerShell-сторона.
- `.run/streamlit.log` — stdout/stderr Streamlit-процесса (`nohup`-redirect).

Три файла имеют три независимых owner'а и три независимых retention-политики. Новые записи из Python-кода идут только в `.run/app.log`.

---

## 7. Changelog этого документа

- 2026-04-19: первая ревизия. Канонизирует текущее состояние `logger.py`, runtime-retention механик и фиксирует гэпы в retention для `paragraph_boundary_reports/`, `relation_normalization_reports/`, `paragraph_boundary_ai_review/`, `structure_maps/`, `structure_validation/`. Описан паттерн добавления новых событий.
- 2026-04-19 (follow-up): гэп закрыт. Введён `runtime_artifact_retention.py` с `prune_artifact_dir()` и per-family константами. Writers подключены. Добавлено DEBUG-событие `artifact_pruned`. Ручной скрипт `scripts/clean-stale-run-artifacts.sh` очищает whitelisted stale root-файлы `.run/`. Тесты: `tests/test_runtime_artifact_retention.py`. Применена первичная cleanup-волна: `.run/` с 24 MiB сжат до 5.5 MiB, 39 stale артефактов удалено, bounded-директории в пределах квот.
