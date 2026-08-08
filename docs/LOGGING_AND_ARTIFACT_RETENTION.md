# Logging and Artifact Retention Contract

Статус: каноническая документация.
Последняя ревизия: 2026-08-04.
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

**Расхождение практики и документа, зафиксировано 2026-08-01 и ждёт решения владельца.** Правило выше сформулировано через список модулей, а пункт 8 чек-листа §4 — через условие «нижний слой без прямого импорта `logger`». Ни та, ни другая формулировка не отвечает на вопрос, что делать модулю, который импортирует логгер напрямую и в списке не значится. Пакет `src/docxaicorrector/generation/` поступает именно так: `resolve_owned_diagnostics_scope` в `src/docxaicorrector/generation/formatting_diagnostics_retention.py` берёт глобальный `log_event`, ровно как это давно делает соседний `src/docxaicorrector/generation/formatting_transfer.py`. То есть это сложившийся стиль пакета, а не регрессия одной функции. Внешнее ревью прочитало это как нарушение — значит, текст допускает два прочтения. Развилка: либо документ признаёт прямой импорт нормой для верхних и средних слоёв и оставляет инъекцию обязательной только там, где её требует тестируемость, либо инъекция объявляется обязательной везде и пакет `generation/` приводится к ней целиком. Второе — это правка кода, а не документации, и по объёму тянет на отдельную спеку. До решения новые функции в `generation/` пишите в стиле пакета: расхождение внутри одного модуля хуже, чем расхождение между модулем и документом.

### 1.5 Когда НЕ логировать

- Не пишите `log_event` на каждую итерацию UI fragment'а (render-цикл Streamlit). Для UI-видимых активностей используйте append-log events в runtime state (`append_log` / `append_image_log`) — их читает журнал обработки.
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
- `persisted_source_validation_failed` — `restart_store.py`, WARNING: persisted restart/completed source отклонён и не может быть восстановлен. Context: `{reason, filename, source_token, storage_kind}`, где `reason` ∈ `{invalid_metadata, unconfined_path, unreadable_payload, integrity_mismatch}`.

### 3.3 Document pipeline (main loop)

- `processing_started` (INFO, run boundary).
- `block_plan_summary` (INFO) + `block_plan_detail` (DEBUG).
- `block_started` (DEBUG), `block_completed`, `block_failed`, `block_rejected`.
- `empty_processed_block`, `structurally_insufficient_processed_block`, `processed_block_count_mismatch`.
- `block_marker_registry_built`, `block_marker_registry_failed`, `marker_diagnostics_artifact_created`.
- `image_placeholder_integrity_failed`, `image_placeholder_mismatch`, `image_processing_failed`.
- `docx_build_failed`, `empty_docx_bytes`.
- `formatting_diagnostics_artifacts_detected`.
- `formatting_diagnostics_write_failed` — `formatting_diagnostics_retention.py`, WARNING: артефакт diagnostics не записан, run продолжается (fail-open). Context: `{stage, expected_dir, scope, run_id, source_token, error_type, error}`.
- `formatting_diagnostics_identity_missing` — `src/docxaicorrector/generation/formatting_diagnostics_retention.py` (`resolve_owned_diagnostics_scope`), WARNING: артефакт пишется, но `run_id` и/или `source_token` пустые, поэтому его ownership понижается с `live` до `offline`. Файл останется на диске, а вот собрать его обратно в отчёт этого прогона уже нельзя — ownership-фильтр его не увидит. Событие существует именно затем, чтобы потеря доказательства не была бесшумной: до спеки 051 понижение происходило молча и «нулевая» метрика формата выглядела как идеальный результат. Context: `{stage, artifact_kind, missing_identity_fields, downgraded_scope}`.
- `processing_run_identity_missing` — `src/docxaicorrector/pipeline/setup.py` (`_warn_on_missing_run_identity`), WARNING через инъецированный `log_event`: run стартует с пустым `run_id`/`source_token`. Не поднимает исключение — offline-прогоны и replay законно живут без идентичности. Это событие потом читает `src/docxaicorrector/validation/structural.py`, чтобы отличить «диагностики не было» от «диагностику потеряли», и на этом основан check `formatting_diagnostics_evidence_not_lost`.
- `invalid_processing_job`, `invalid_processing_plan`, `processing_init_failed`.
- `ui_result_artifacts_saved`, `ui_audiobook_artifact_saved`.
- `ui_result_artifacts_save_failed` — `late_phases.py`, WARNING: primary result files (markdown + docx) не дошли до диска. Context: `{filename, error_message}`.
- `reader_cleanup_diagnostics_save_failed` — `late_phases.py`, WARNING: secondary diagnostics не сохранены; primary result при этом остаётся доставленным.
- `segment_result_registry_saved` (INFO) / `segment_result_registry_save_failed` (WARNING) — `late_phases.py`: persisted segment result registry пишется ПОСЛЕ primary result files, его отказ не переводит run в unpersisted.
- `segment_result_records_build_failed` — `late_phases.py` (`finalize_processing_success`), WARNING: сборка записей segment result registry упала уже после доставки результата. Теряется только кэш для возобновления, доставленный результат остаётся доставленным. Context: `{filename, error_type, error_message}`.
- `post_delivery_secondary_step_failed` — `late_phases.py` (`_log_post_delivery_secondary_failure`), WARNING: внешний страховочный обработчик вокруг всего блока вторичных записей после доставки результата. Ловит всё, что не поймали частные обработчики выше, и намеренно НЕ перевыбрасывает: до спеки 051 такое исключение обнуляло уже доставленный документ и предлагало пользователю оплатить повторный прогон. Сам вызов логгера обёрнут в `except Exception: pass` — отказ логирования не должен воскресить исходную проблему.
- `audiobook_postprocess_chunk_started`, `audiobook_postprocess_chunk_completed`.
- `narration_artifact_review_data` — `src/docxaicorrector/pipeline/late_phases.py`, WARNING: в готовом narration-тексте остались фрагменты, которые стоит просмотреть человеку (ссылочные маркеры, DOI/ISBN/arXiv-идентификаторы, немоделируемые теги). **Это review DATA, а не отказ**: артефакт доставляется, прогон завершается успешно, событие лишь называет причину посмотреть. До спеки 054 та же проверка бросала исключение и на standalone-прогоне `audiobook` уничтожала весь артефакт после полностью оплаченного LLM-прогона; четыре из шести её правил, как было измерено 2026-08-04, срабатывают на обычной прозе, а Конституция VII требует отдавать остаток как review data, а не как жёсткий вердикт. Событие эмитится ровно один раз на прогон и только когда есть что показать — на чистом тексте его нет вовсе, а нулевой результат проверки виден в `ui_audiobook_artifact_saved` (§5.5). Context: `{filename, processing_operation, narration_mode, review_data, advisory, narration_chars, review_finding_count, review_match_count, review_rules, review_findings}`, где `narration_mode` ∈ `{standalone, postprocess}` (два входа в narration: операция `audiobook` и опциональный post-pass на `edit`/`translate`), `review_finding_count` — число СРАБОТАВШИХ правил, `review_match_count` — суммарное число совпадений, а `review_findings` — по записи на правило вида `{rule, match_count, samples}`. `samples` — максимум 3 фрагмента на правило, каждый обрезан до 120 символов: на книге одно правило даёт сотни совпадений (измерено 196 и 178), и в лог не должен попадать payload модели (§1.5).
- `narration_source_fallback_excluded` — `src/docxaicorrector/pipeline/late_phases.py`, WARNING: сколько блоков и символов НЕ попало в narration-артефакт потому, что вывод модели для них был отвергнут и controlled fallback подставил ИСХОДНЫЙ текст блока (`src/docxaicorrector/pipeline/block_execution.py`, `fallback_delivered_source_text`). Артефакт озвучки содержит только произносимый текст на целевом языке, поэтому такой блок в него не идёт; в DOCX исходный текст остаётся — это редактируемый документ, где человек увидит непереведённый абзац и починит его, а между аудиокнигой и слушателем редактора нет. Асимметрия намеренная, но потеря обязана быть видимой: событие идёт тем же маршрутом, что и `narration_artifact_review_data` (§3.3) — WARNING-событие, user-facing notice `result.narration_source_fallback_excluded` и счётчики на записи о сохранённом файле (§5.5). Эмитится ровно один раз на прогон и только когда исключён хотя бы один блок; ноль исключённых блоков — это отсутствие события, а не событие с нулём. Context: `{filename, processing_operation, narration_mode, review_data, advisory, narration_chars, excluded_source_fallback_block_count, excluded_source_fallback_chars}`. Измерено на первом живом audiobook-прогоне 2026-08-04 (Money & Sustainability, en→ru): 6 блоков / 20 597 символов английского текста доехали до озвучки как есть.
- `narration_omitted_paragraphs_excluded` — `src/docxaicorrector/pipeline/late_phases.py`, WARNING: сколько АБЗАЦЕВ и символов не попало в narration-артефакт потому, что модель не вернула для них текст (статус `omitted`, спека 056 E). Пер-абзацный близнец `narration_source_fallback_excluded` и идёт тем же маршрутом: WARNING-событие, user-facing notice `result.narration_omitted_paragraphs_excluded` и счётчики состояния прогона. Введён потому, что пер-абзацное средство оказалось ТИШЕ блочного отказа, который оно заменило: `omitted` публиковал только счёт абзацев и не давал уведомления, тогда как блочный путь публиковал символы и уведомлял. Средство, уменьшающее потерю, не имеет права уменьшать её видимость. Эмитится ровно один раз на прогон и только когда исключён хотя бы один абзац. Context: `{filename, processing_operation, narration_mode, review_data, advisory, narration_chars, excluded_omitted_paragraph_count, excluded_omitted_paragraph_chars}`.
- `model_usage_accounted` — `src/docxaicorrector/pipeline/_pipeline.py` (`emit_run_model_accounting_event`), INFO через инъецированный `log_event`: сколько токенов и денег стоил прогон, сколько было повторных попыток и сколько ответов модели отброшено в пользу исходника. Эмитится ровно один раз на прогон, из `finally` вокруг `run_document_processing`, поэтому **упавший прогон тоже отчитывается** — деньги тратятся на вызов, а не на успешный исход. Context: `{filename, accounting_scope, run_id, source_token, run_identity_complete, model_call_count, model_calls_with_usage, model_calls_without_usage, model_calls_without_cost, prompt_tokens, completion_tokens, total_tokens, cost_usd_reported_by_provider, token_accounting_complete, cost_accounting_complete, retry_attempt_count, retried_block_count, retried_paragraph_count, retry_reason_counts, model_output_discarded_paragraph_count, model_output_discarded_block_count, model_output_discarded_reason_counts, paragraph_disposition_counts, controlled_block_fallback_block_count, controlled_block_fallback_chars, controlled_block_fallback_kind_counts, controlled_block_fallback_kind_chars, degradation_ladder_block_count, degradation_ladder_model_call_count, degradation_ladder_translated_paragraph_count, degradation_ladder_unrescued_paragraph_count, degradation_ladder_sentence_split_paragraph_count, degradation_ladder_oversized_sentence_count, degradation_ladder_trigger_counts, stages, preparation_accounting, unscoped_model_call_count}`. Четвёрка `controlled_block_fallback_*` — ПАЙПЛАЙНОВАЯ половина той же потери: блоки, которые `process_single_block` признал негодными и всё равно доставил (решение `fallback_continue` в `CONTROLLED_BLOCK_FAILURE_POLICY`, `src/docxaicorrector/pipeline/block_execution.py`). Это отдельное семейство, а не ещё одна причина в `model_output_discarded_*`: там учитывается решение ГЕНЕРАТОРА выбросить ответ модели, и на одном и том же блоке оба решения принимаются подряд — на прогоне 2026-08-06 Money & Sustainability генератор записал `marker_validation_source_fallback: 2`, а пайплайновая ветка сработала на тех же двух блоках, так что слияние семейств показало бы 4 блока вместо двух. Символы считаются наравне с блоками, потому что объём подставленного текста и есть цена дефекта, а блоки различаются на порядок; `..._kind_counts` и `..._kind_chars` разложены по `fallback_kind` из той же таблицы и суммируются ровно в две тотальные величины. Пустые словари рядом с нулевыми тоталами означают «ни один блок туда не пошёл» — та же форма, что у `model_output_discarded_reason_counts`. `paragraph_disposition_counts` (спека 056 E) — что стало с каждым абзацем marker-блоков за прогон: `{accepted, omitted, retry_required, source_restored}`. Все четыре ключа присутствуют ВСЕГДА; ноль здесь — утверждение «в эту корзину ничего не попало», а не отсутствие поля. `accepted` — текст модели; `omitted` — модель не вернула ничего для этого абзаца, в DOCX остаётся исходный текст, в озвучку абзац не попадает; `source_restored` — текст модели отброшен (виден merge в соседа) и восстановлен исходник абзаца; `retry_required` — промежуточный статус внутри цикла попыток, наружу он не выходит и в отчёте прогона обычно равен нулю. Это же место, где человек видит итог: событие в `.run/app.log` и ключ `model_accounting` в `.run/ui_results/<stem>.meta.json` (§5.5).
  Семёрка `degradation_ladder_*` — ЛЕКАРСТВО рядом с двумя мерами потери, которую оно убирает. `..._block_count` — сколько блоков генератор ответил ДЕЛЕНИЕМ вместо подстановки исходника; `..._trigger_counts` раскладывает их по причине (`marker_contract` \ `incomplete_response`); `..._model_call_count` — цена, измеренная как дельта собственного счётчика вызовов ledger'а вокруг лестницы, а не оценённая по числу абзацев (абзац, потребовавший двух попыток, стоил два вызова); `..._translated_paragraph_count` и `..._unrescued_paragraph_count` в сумме дают число абзацев этих блоков и вместе называют весь исход — сколько прозы спасено и сколько осталось в документе на языке источника. Имя `unrescued`, а не `source_restored`, намеренно: абзац, который лестница не вытянула, получает статус `omitted` (озвучка его удерживает), тогда как `source_restored` — статус ремонта merge'а, который озвучка ПРОИЗНОСИТ; путать две величины нельзя. `..._sentence_split_paragraph_count` — абзацы, которые пришлось делить ниже маркера, по предложениям, со склейкой обратно в тот же абзац; `..._oversized_sentence_count` — названный честный край: предложение, чей ответ не помещается под потолок `max_output_tokens`, глубже не делится. Ноли здесь — утверждение «лестница не включалась»; это и есть анти-вакуумная проверка, потому что на блоке, прошедшем с первой попытки, она обязана не стоить ни одного вызова (Конституция VIII).
  Честность контракта: токены и стоимость берутся ТОЛЬКО из `usage` ответа провайдера (OpenRouter отдаёт ещё и `cost` в USD на вызов) — прайс-лист в коде не подставляется никогда. Вызов, чей ответ не принёс `usage`, увеличивает `model_calls_without_usage` и добавляет ноль токенов, поэтому пару `total_tokens=0` и `token_accounting_complete=false` нельзя прочитать как «бесплатно»: это «неизвестно». То же для `cost_accounting_complete`.
  Принадлежность прогону: учёт привязан к идентичности прогона, а не к глобальному reset'у. `run_document_processing` открывает `run_model_accounting_scope(run_id, source_token)` — у скоупа свой ledger, поэтому второй прогон, допущенный одновременно (лимит по умолчанию — 2), не может ни обнулить, ни разделить эти счётчики. `run_id`/`source_token` в контексте называют прогон, к которому относится снимок; `run_identity_complete=false` означает лишь, что снимок нельзя ИМЕНОВАТЬ (изоляция от этого не зависит).
  `preparation_accounting` — расход стадии preparation (paragraph-boundary AI review) того же `source_token`, снятый рядом с прогоном и **не входящий** в его тоталы (`included_in_run_totals: false`): preparation идёт в отдельном worker'е до старта прогона и одна подготовка может обслужить несколько прогонов одного источника, поэтому сложение приписало бы одну и ту же работу дважды. `null`, если для этого источника подготовка не выполнялась в этом процессе. `unscoped_model_call_count` — вызовы, записанные вне какого-либо скоупа: «расход, который никто не заявил», как читаемое число, а не как молчание.
  Разбивка `stages` — по точке вызова (`text_generation`, `boundary_review`, `image_analysis`, `image_validation`, `image_reconstruction`, `image_generation`, `unattributed`), а не по режиму прогона: режим (перевод / литредактирование / вычитка) — свойство прогона целиком и читается из `processing_started`.
- `processing_completed` (INFO, run boundary).
- `processing_completed_unpersisted` — `late_phases.py`, WARNING, альтернативный run boundary: документ обработан, но primary result files не сохранены. Context: `{reason}` + те же поля, что у `processing_completed`.

### 3.4 Generation

- `context_leakage_persisted`, `image_only_target_passthrough`.
- `markdown_empty_response_recovery_started`, `markdown_incomplete_response_source_fallback`, `markdown_empty_response_source_fallback`.
- `marker_paragraph_omitted` — `src/docxaicorrector/generation/_generation.py`, WARNING: модель не вернула текст для отдельных абзацев блока (спека 056 E). Раньше это отбрасывало ВЕСЬ блок и подставляло его английский исходник; теперь блок сохраняет остальные абзацы, а эти получают статус `omitted`. Context: `{omitted_paragraph_ids, omitted_paragraph_count, omitted_source_chars, paragraph_count}`. `omitted_source_chars` обязателен: мерило спеки 054 — доля символов исходного языка в артефакте, и счётчик абзацев с ним не сопоставим — на блоке 174 прогона 2026-08-04 одна строка «1 абзац» стояла за 1 378 символов.
- `marker_chunk_paragraph_break_collapsed` — `src/docxaicorrector/generation/_generation.py`, INFO: модель разбила единственный абзац блока на несколько; части склеены обратно в один абзац. Эмитится только там, где присвоение текста доказуемо однозначно, и таких мест ровно два: блок с ОДНИМ маркером и одиночный запрос лестницы деградации (ниже), который по построению нёс один абзац. Context: `{paragraph_id, part_count, collapsed_chars}`.
- `degradation_ladder_started` \ `degradation_ladder_completed` — `src/docxaicorrector/generation/_generation.py`, WARNING: блок отвергнут после recovery, и вместо подстановки исходного текста генератор ПЕРЕСПРАШИВАЕТ его частями. Два триггера: `marker_contract` (контракт маркеров нарушен — пакетирование снимается, каждый абзац спрашивается отдельно с `marker_mode=False`, где класс ошибки недостижим по построению) и `incomplete_response` (отказ по РАЗМЕРУ — `_boost_request_output_budget` упирается в `_MODEL_OUTPUT_TOKEN_CEILING`, поэтому помогает только деление). Context started: `{trigger, block_index, unit_count, marker_mode}`; completed: `{trigger, block_index, unit_count, translated_unit_count, unrescued_unit_count, model_call_count}`. События эмитятся только когда лестница ДЕЙСТВИТЕЛЬНО делит запрос: блок, прошедший с первой попытки, и блок из одного нечленимого предложения не стоят ни одного лишнего вызова.
- `degradation_ladder_sentence_split` — там же, INFO: абзац снова вернулся `incomplete_response`, и он делится по предложениям с обратной склейкой В ТОТ ЖЕ абзац. Маркер при этом не создаётся и не уничтожается, число абзацев блока инвариантно. Context: `{paragraph_chars, group_count}`.
- `degradation_ladder_sentence_exceeds_output_ceiling` — там же, WARNING, честный предел лестницы: одно предложение само превышает объём, который вообще можно забюджетировать под потолком `max_output_tokens`, а ниже предложения деления нет. Предложение всё равно спрашивается; если и оно не отвечено, в документе остаётся ИСХОДНЫЙ текст этого абзаца (и только его) со статусом `omitted` — молчаливой подстановки не происходит, число видно в `degradation_ladder_oversized_sentence_count`. Context: `{paragraph_chars, sentence_chars?, budgetable_chars}`.
  Статус абзаца, который лестница не смогла перевести, — именно `omitted`, а не `source_restored`, и выбор вынужденный: вниз по течению эти два статуса различаются ровно одним — `narration_projection_for_processed_block` УДЕРЖИВАЕТ `omitted` и ПРОИЗНОСИТ `source_restored`. Блочный fallback, перед которым стоит лестница, выбрасывается из озвучки целиком (`fallback_delivered_source_text`), поэтому `source_restored` на остатке означал бы, что ЧАСТИЧНОЕ спасение читает вслух больше английского, чем полное его отсутствие. `omitted` при этом описывает исход правдиво: исходный текст абзаца остаётся в DOCX (ничего не потеряно, отображение «маркер — абзац» цело), а в озвучку он не идёт.
- `model_empty_response_shape`, `prompt_quality_warning`.
- `marker_attempt_rejected` — `src/docxaicorrector/generation/marker_attempt_capture.py`, WARNING: ответ модели отклонён проверкой маркеров абзацев (спека 056, решение D′). Эмитится по КАЖДОЙ отклонённой попытке, включая последнюю и recovery-вызов, из цикла попыток `generate_markdown_block` — то есть и тогда, когда блок затем уходит в controlled fallback и наружу возвращается обычная строка. Context: `{block_index, attempt, max_attempts, stage, error_code, expected_paragraph_ids, found_paragraph_ids, raw_response_chars, target_chars, artifact_path}`. `stage` — `attempt` (внутри цикла) или `recovery` (последний, informed вызов). Сам ответ модели в лог НЕ попадает (§1.5): он лежит целиком, без усечения, в артефакте `.run/marker_attempts/*.json` (§5.1), схема `{schema_version, block_index, attempt, max_attempts, stage, error_code, expected_paragraph_ids, found_paragraph_ids, target_chars, raw_response_chars, raw_response, leading_text, note}`. Директорию не читает ни одна стадия пайплайна — это forensic-запись для человека, чтобы отклонённый ответ можно было переиграть офлайн, а не покупать новый прогон. `artifact_path: null` означает, что запись на диск не удалась; событие всё равно эмитится.

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
- `result_bundle_invalid_delivery_disposition` — `processing_runtime.py`, WARNING: сохранённый `delivery_disposition` невалиден (неизвестный status или `blocked` без explanation); bundle рендерится с safe accepted fallback вместо падения frame'а. Context: `{error}`.

### 3.7 Reader cleanup post-pass

- `reader_cleanup_global_plan_started|completed`, `reader_cleanup_chunk_started|completed`, `reader_cleanup_schema_repair_started|completed` — `reader_cleanup_postprocess.py`, INFO.
- `reader_cleanup_noop`, `reader_cleanup_applied` — `reader_cleanup_postprocess.py`, INFO (terminal-переходы post-pass).
- `reader_cleanup_drop_back_matter_unsupported` — `reader_cleanup_postprocess.py`, WARNING.
- `reader_cleanup_strict_failed_base_result_preserved`, `reader_cleanup_failed_base_result_preserved` — `reader_cleanup_postprocess.py`, WARNING: post-pass упал, но base result доставлен.
- `reader_cleanup_failed` — `reader_cleanup_postprocess.py`, через `present_error` (ERROR + traceback).
- `reader_cleanup_failed_chunk_ratio_exceeded` — `reader_cleanup_postprocess.py`, WARNING: доля упавших чанков вычитки превысила `max_failed_chunk_ratio`, проход прерван, не применено ничего. Пользователь получает не общий совет «результат доступен частично», а конкретную причину с числами. Context несёт долю и порог. Обратите внимание: та же строка встречается в `src/docxaicorrector/reader_cleanup_mvp/service.py` внутри `warnings` отчёта — там это не log event, а payload-строка, порождающая условие для события выше.
- `reader_cleanup_image_anchor_lost_cleanup_discarded` — `reader_cleanup_postprocess.py`, WARNING: применение принятых операций теряло якоря картинок в DOCX, а виновную операцию изолировать не удалось, поэтому отброшена вся вычитка целиком. Документ доставляется без изменений, но со всеми картинками. Context: `{missing_image_id_count, discarded_cleanup_operation_count}`.
- `reader_cleanup_anchor_repair_discarded_for_missing_image_anchor` — `reader_cleanup_postprocess.py`, WARNING, две точки эмиссии: подпроход починки якорей откачен, а остальная вычитка при этом либо не изменила ничего, либо доставлена. Уровень WARNING, а не ERROR, потому что стадия завершается штатно (`stage_status = completed`).

Строки вида `reader_cleanup_*` внутри reader-cleanup MVP `service.py` и check-имя `reader_cleanup_stage_completed` в `acceptance.py` — это warning-строки report payload и имя acceptance-check, а НЕ log events; не заводите их как event-имена.

### 3.8 Зарегистрированы по имени, но ещё не описаны

Сверка каталога с кодом 2026-08-01 показала, что §3.1–§3.7 покрывают не все события: код эмитит
их больше, чем описано здесь. Перечисленные ниже 59 имён **заняты** — этого достаточно, чтобы
пункт 1 чек-листа §4 (не заводить дубликат имени) работал честно. Описание уровня, смысла и
context-ключей добавляется для события, когда его модуль в следующий раз меняют: выдумывать
семантику по имени было бы ровно тем враньём документации, против которого этот документ и написан.

- `src/docxaicorrector/document/layout_cleanup.py`: `layout_artifact_cleanup_outcome`.
- `src/docxaicorrector/generation/_generation.py`: `markdown_marker_validation_source_fallback`, `markdown_non_completed_response_source_fallback`, `provider_text_api_fallback_engaged`.
- `src/docxaicorrector/generation/formatting_restoration.py`: `alignment_restoration_skipped`.
- `src/docxaicorrector/generation/formatting_transfer.py`: `paragraph_count_mismatch_restore`, `paragraph_count_mismatch_preserve` (имя передаётся параметром `mismatch_event_name`).
- `src/docxaicorrector/image/analysis.py`: `image_analysis_skipped_over_budget`, `image_document_pixel_budget_exceeded`, `image_encoded_byte_budget_exceeded`, `image_pixel_budget_decompression_bomb`, `image_pixel_budget_exceeded`.
- `src/docxaicorrector/image/generation.py`: `image_generation_skipped_over_budget`.
- `src/docxaicorrector/image/pipeline.py`: `image_compare_variant_failed`, `image_document_pixel_budget_skip`, `image_fallback_applied`, `image_processing_budget_exhausted`, `image_processing_skipped_unsupported_source`, `image_validation_advisory_accept`, `semantic_candidate_attempt_failed`, `semantic_candidate_budget_exhausted`, `semantic_candidate_evaluated`, `semantic_candidate_resolved_to_safe_fallback`.
- `src/docxaicorrector/pdf_import/images.py`: `pdf_image_extraction_dropped_images`, `pdf_image_extraction_page_budget_exceeded`, `pdf_image_extraction_summary`.
- `src/docxaicorrector/pipeline/block_execution.py`: `block_controlled_fallback`, `controlled_fallback_registry_build_failed`, `toc_prompt_routing_selected`, `toc_validation_rejected`.
- `src/docxaicorrector/pipeline/block_failures.py`: `toc_validation_failed_terminal`.
- `src/docxaicorrector/pipeline/job_results.py`: `job_result_registry_save_failed`.
- `src/docxaicorrector/pipeline/late_phases.py`: `audiobook_postprocess_failed`, `audiobook_postprocess_failed_base_result_preserved`, `boundary_recovery_diagnostics`, `quality_report_saved`, `translation_quality_gate_failed`, `translation_quality_gate_failed_post_cleanup`. События `audiobook_artifact_validation_failed` и `audiobook_artifact_validation_failed_base_result_preserved` УДАЛЕНЫ спекой 054 вместе с гейтом, который их порождал; их заменяет описанный в §3.3 `narration_artifact_review_data`. `audiobook_postprocess_failed*` остаются и относятся к другому классу — post-pass, который не удалось выполнить (в том числе `narration_cleanup_projection_unsafe:*`), а не к «грязному» тексту.
- `src/docxaicorrector/pipeline/quality_report_retention.py`: `quality_report_write_failed`.
- `src/docxaicorrector/pipeline/terminal_results.py`: `empty_processing_plan`.
- `src/docxaicorrector/processing/application_flow.py` (все через `fail_critical_fn`, то есть CRITICAL + прерывание): `doc_conversion_failed`, `doc_validation_failed`, `empty_target_block`, `no_jobs_built`, `quality_gate_blocked`.
- `src/docxaicorrector/processing/preparation.py`: `preparation_outcome`.
- `src/docxaicorrector/processing/processing_runtime.py`: `materialized_upload_cache_hit`, `pdf_import_over_budget`, `pdf_text_layer_image_extraction_failed`, `pdf_text_layer_image_render_dropped`, `pdf_text_layer_import_succeeded`.
- `src/docxaicorrector/processing/processing_service.py` (через `present_error_fn`): `preparation_worker_crashed`, `processing_worker_crashed`.
- `src/docxaicorrector/processing/restart_store.py`: `restart_source_delete_refused`.
- `src/docxaicorrector/processing/upload_ports.py`: `heartbeat_callback_failed`.
- `src/docxaicorrector/runtime/state.py`: `completed_source_store_failed`.
- `src/docxaicorrector/ui/application_flow.py`: `document_prepared`.

### 3.9 Чего `scripts/_list_log_events.py` не видит

Скрипт полезен, но он не является полным индексом, и полагаться на его молчание нельзя. Проверено
2026-08-01, три слепые зоны:

1. **Инъецированные логгеры.** Регулярка ищет `log_event(`, а не `log_event_fn(` /
   `present_error_fn(` / `fail_critical_fn(` / `dependencies.log_event(`. Из-за этого выпадают целые
   модули — `src/docxaicorrector/processing/application_flow.py`, `src/docxaicorrector/ui/application_flow.py`, `src/docxaicorrector/image/pipeline.py`,
   `src/docxaicorrector/runtime/state.py`, `src/docxaicorrector/core/config_model_registry.py` — притом что §1.4 предписывает нижним слоям
   именно инъекцию. Инструмент аудита не видит того, что документ рекомендует как правильный стиль.
2. **Имена в константах.** `formatting_diagnostics_identity_missing` и
   `processing_run_identity_missing` объявлены константами, а не литералами в вызове, и скрипт их
   не находит.
3. **Захардкоженный список файлов.** `TARGETS` перечисляет модули поимённо, отсутствующие файлы
   пропускаются молча; новый модуль в индекс не попадёт, пока его туда не впишут руками.

Пока это так, сверять новое имя нужно и с §3, и грепом по `src/`, а не одним скриптом.

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
| `.run/formatting_diagnostics/*.json` | TTL 7 дней, max 100 файлов, pruning при каждой записи. Retention family-wide и НЕ зависит от ownership envelope | `formatting_diagnostics_retention.prune_formatting_diagnostics()` |
| `.run/paragraph_boundary_reports/*.json` | TTL 7 дней, max 300 файлов, pruning при каждой записи | `document._write_paragraph_boundary_report_artifact()` → `runtime_artifact_retention.prune_artifact_dir()` |
| `.run/relation_normalization_reports/*.json` | TTL 7 дней, max 300 файлов, pruning при каждой записи | `document._write_relation_normalization_report_artifact()` → `prune_artifact_dir()` |
| `.run/paragraph_boundary_ai_review/*.json` | TTL 14 дней, max 200 файлов, pruning при каждой записи | `document._write_paragraph_boundary_ai_review_artifact()` → `prune_artifact_dir()` |
| `.run/structure_maps/*.json` | TTL 30 дней, max 200 файлов, pruning при каждой записи | `preparation._write_structure_map_debug_artifact()` → `prune_artifact_dir()` |
| `.run/structure_validation/*.json` | TTL 30 дней, max 200 файлов, pruning при каждой записи | `structure_validation.write_structure_validation_debug_artifact()` → `prune_artifact_dir()` |
| `.run/document_topology/*.json` | TTL 30 дней, max 200 файлов, pruning при каждой записи | `preparation._write_document_topology_debug_artifact()` → `prune_artifact_dir()` |
| `.run/marker_attempts/*.json` | TTL 7 дней, max 400 файлов, pruning при каждой записи | `src/docxaicorrector/generation/marker_attempt_capture.py :: write_marker_attempt_artifact()` → `prune_artifact_dir()` |
| `.run/ui_results/*` | TTL 7 дней, max 80 result stems, pruning grouped by stem при каждой записи | `runtime_artifacts.write_ui_result_artifacts()` → `prune_ui_result_artifact_groups()` |
| `.run/restart_*`, `.run/completed_*` | TTL 12 часов, cleanup при старте приложения | `restart_store.cleanup_stale_persisted_sources`, вызов из `app._schedule_stale_persisted_sources_cleanup` |
| `.run/project.log` | Size-rollover на PowerShell-стороне (`Invoke-ProjectLogRollover`), backupCount=5, порог `256 KiB` | `scripts/_shared.ps1` |
| `.run/streamlit.log` | Size-rollover в WSL control-скрипте, backupCount=5, порог `256 KiB`, check каждые 30s | `scripts/project-control-wsl.sh :: rotate_streamlit_log_if_needed` |
| stale ad-hoc root файлы (`full_pytest_*.txt`, `wrapper-*.{out,exit}`, `min*.ps1`, `shared-fragment.ps1`, …) | Legacy debt only. Ручная очистка whitelisted patterns старше `--min-age-days` (по умолчанию 14) | `scripts/clean-stale-run-artifacts.sh` (`--apply` чтобы выполнить) |
| `.run/manual_investigations/<topic>/*` | Canonical ignored area for manual local investigation evidence and ad-hoc debug snapshots. No runtime pruning guarantee; owner is the human/agent that created the evidence. | Manual placement under `.run/`; migrate from repo root instead of leaving files in workspace root |

Все эти механики трогают строго свои файлы и не ходят в `tests/artifacts/...`.

Root workspace is not an artifact drop zone. Runtime/debug/manual investigation artifacts must live either under a specialized ignored `.run/<family>/...` directory or under `.run/manual_investigations/<topic>/...`. Accepted versioned regression fixtures live only under `tests/artifacts/...`; do not leave diagnostic JSON/TXT/PY outputs in the repo root and do not legitimize new root clutter by adding more root-level ignore patterns.

Политики per-family зафиксированы как константы в `runtime_artifact_retention.py` — это **единственный source of truth** для TTL/count. Writers импортируют оттуда нужную пару значений и вызывают `prune_artifact_dir(target_dir=..., max_age_seconds=..., max_count=...)` сразу после записи нового файла. Pruner является synchronous, filesystem-only, no-op для отсутствующей директории.

### 5.2 Поведение pruner'а

- Никогда не ходит выше `.run/<dir>/`.
- Не трогает subdirectories — только файлы matching `glob` (по умолчанию `*.json`).
- Не трогает файлы, принадлежащие текущему процессу (PID-файлы, `app.ready`, текущий `app.log`) — они находятся в корне `.run/`, а pruner вызывается только для artifact-поддиректорий.
- No-op если директория не существует или не содержит matching файлов.
- На каждом фактическом удалении (если было хоть одно) эмитит DEBUG-event `artifact_pruned` с контекстом `{dir, removed_count, max_age_seconds, max_count}`. Writers могут отключить логирование через `emit_log=False`, если артефакт-путь уже освещён событием более высокого уровня.
- Сначала отбрасываются файлы старше `max_age_seconds`; затем, если превышен `max_count`, удаляются самые старые по mtime (tiebreaker — имя файла). Это делает pruning детерминистичным.
- Для `.run/ui_results/` retention действует по stem-group: `.result.md`, `.result.docx` и optional `.result.tts.txt` сохраняются и удаляются как единая группа, чтобы не оставлять orphaned narration/download artifacts.
- Для `.run/formatting_diagnostics/` каждый артефакт несёт ownership envelope `{scope: "live"|"offline", run_id, source_token}` — и в payload (`ownership`), и в имени файла (`<stem>_<run_id>_<source_token>_<epoch_ms>_<uuid>.json` для `live`, `<stem>_offline_<epoch_ms>_<uuid>.json` для `offline`). Live-сборка (`collect_owned_formatting_diagnostics`) отбирает только `scope == "live"` с точным совпадением `run_id` И `source_token`; неполный legacy-контекст не владеет ничем и НЕ расширяется до directory-wide или time-window discovery. Ownership влияет только на collection — retention остаётся family-wide (7 дней / 100 файлов).

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

Дополнительные правила размещения:

1. Repo root не использовать как drop zone для diagnostic JSON/TXT/PY artifacts, manual comparison scripts или investigation snapshots.
2. Если локальное расследование требует сохранить evidence, переносить его в `.run/manual_investigations/<topic>/...`, а не оставлять в корне workspace.
3. Если артефакт стал намеренно versioned regression fixture, он должен жить только в `tests/artifacts/...`; не держать accepted fixtures в корне и не маскировать их root-level ignore rules.
4. Если для новой artifact family нужен долгоживущий ignored path, сначала выбрать специализированную `.run/<family>/` директорию и описать её cleanup/retention story в этом документе.

### 5.5 Разграничение persisted source и итогового output

- `.run/restart_*` и `.run/completed_*` относятся к persisted source cache и содержат байты исходного загруженного файла, а не итоговый результат обработки.
- Итоговые user-visible output files для обычных UI-прогонов живут в `.run/ui_results/`.
- Канонический runtime-event для итоговых UI output files: `ui_result_artifacts_saved` с контекстом `artifact_paths={markdown_path, docx_path}` или `artifact_paths={markdown_path, docx_path, tts_text_path}`.
- Дополнительный narration-specific signal: `ui_audiobook_artifact_saved` использует тот же envelope-style контекст с `filename` и `artifact_paths`, а дополнительно несёт `tts_text_path`, `char_count`, `tag_count`, `excluded_blocks`, `mode`, `excluded_source_fallback_block_count`, `excluded_source_fallback_chars`, `excluded_omitted_paragraph_count`, `excluded_omitted_paragraph_chars`, `review_finding_count`, `review_match_count`, `review_rules`, `joined_sentence_continuation_count`. Два `excluded_source_fallback_*` — блоки, исключённые из озвучки потому, что вывод модели был отвергнут и подставлен исходный текст (§3.3, `narration_source_fallback_excluded`); они считаются ОТДЕЛЬНО от `excluded_blocks`, который отвечает за решение документного слоя `narration_include`, — вопросы разные, и измерения exclusion спеки 054 привязаны ко второму. Два `excluded_omitted_paragraph_*` — то же самое на уровне АБЗАЦА (§3.3, `narration_omitted_paragraphs_excluded`, спека 056 E): абзацы, для которых модель не вернула текст; они тоже считаются отдельно. Три последних (спека 054) кладут итог narration-проверки на запись о СОХРАНЁННОМ файле: по одной строке лога видно и путь `.result.tts.txt`, и повод его просмотреть. Ноль здесь — это утверждение «проверено, ничего не найдено», а не отсутствие поля; развёрнутые находки с примерами живут в `narration_artifact_review_data` (§3.3). `joined_sentence_continuation_count` (спека 054, 2026-08-06) — единственный narration-счётчик на этой записи, который сообщает не потерю, а ПОЧИНКУ: сколько абзацных границ сборка закрыла потому, что предложение шло через них насквозь (`src/docxaicorrector/generation/_generation.py`, `_narration_paragraph_continues`). Ни один символ при этом не добавляется и не пропадает — `\n\n` становится пробелом, — но операция обязана быть видимой, потому что она меняет доставленный артефакт; отдельного WARNING-события нет именно потому, что это не потеря и просматривать тут нечего. Считается одинаково на обоих входах в narration (standalone `audiobook` и опциональный post-pass, `mode` в этом же контексте). Ноль — это утверждение «в этой книге ни одно предложение не было разорвано абзацной границей», а не отсутствие поля. Измерено офлайн на прогоне четырёх книг 2026-08-06: 5 / 7 / 14 / 8 границ.
- Если нужно восстановить, что именно пользователь видел в финальном download path, начинать надо с `.run/ui_results/` и `ui_result_artifacts_saved`, а не с root-level `.run/completed_*`.
- `<stem>.meta.json` дополнительно несёт ключ `model_accounting` — тот же payload, что у события `model_usage_accounted` (§3.3), снятый в момент записи артефактов. Он кладётся рядом с `quality_warning` и не заводит новой artifact family, поэтому retention `.run/ui_results/` (7 дней / 80 result stems, grouped by stem) на него распространяется без изменений. Ключ отсутствует, если прогон не сделал ни одного вызова модели.

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
- `tests/test_format_restoration.py` — retention по age/count (`test_prune_formatting_diagnostics_*`).
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
- 2026-07-21: каталог догнан до текущего кода. В §3 добавлены `persisted_source_validation_failed`, `result_bundle_invalid_delivery_disposition`, `ui_result_artifacts_save_failed`, `reader_cleanup_diagnostics_save_failed`, `segment_result_registry_saved|_save_failed`, `processing_completed_unpersisted`, расширенный context у `formatting_diagnostics_write_failed` и новая секция §3.7 по reader-cleanup post-pass. В §5.1/§5.2 зафиксирован ownership envelope `{scope, run_id, source_token}` для `.run/formatting_diagnostics/*.json` и scoped live-collection; retention семьи не изменился.
- 2026-08-01: каталог снова догнан до кода. В §3.3 добавлены `formatting_diagnostics_identity_missing`, `processing_run_identity_missing`, `segment_result_records_build_failed`, `post_delivery_secondary_step_failed`; в §3.7 — `reader_cleanup_failed_chunk_ratio_exceeded`, `reader_cleanup_image_anchor_lost_cleanup_discarded`, `reader_cleanup_anchor_repair_discarded_for_missing_image_anchor` (все семь появились со спеками 051 и 052 и не были зарегистрированы, хотя §4 этого требует). Полная сверка показала, что расхождение шире семи имён: заведена §3.8 с ещё 59 событиями, зарегистрированными по имени и модулю, но пока без описания — это честно признанный долг, а не свежая находка. В §3.9 описаны три слепые зоны `scripts/_list_log_events.py`, из-за которых его молчание нельзя считать доказательством. В §1.4 зафиксировано расхождение между правилом об инъекции логгера и практикой пакета `generation/`, требующее решения владельца.
- 2026-08-03: зарегистрирован `model_usage_accounted` (§3.3) — первый учёт токенов и стоимости в продукте. До него в `src/` не было ни одного упоминания `usage`/`prompt_tokens`/`cost`, и цифры прогона книги существовали только потому, что прогон патчил SDK снаружи. В §5.5 описан ключ `model_accounting` в `.run/ui_results/*.meta.json`.
- 2026-08-04: спека 054 — артефакт озвучки содержит только произносимый текст на целевом языке. Добавлено WARNING-событие `narration_source_fallback_excluded` (§3.3), payload `ui_audiobook_artifact_saved` расширен полями `excluded_source_fallback_block_count` / `excluded_source_fallback_chars` (§5.5), добавлен user-facing notice `result.narration_source_fallback_excluded`. Новых artifact-семей и изменений retention нет. Отчёт real-document прогона получил секцию `narration_artifact` и строки `narration_*` в summary, снятые из того же события — тем же способом, что и `model_accounting`, без второго канала.
- 2026-08-06: спека 054 — предложение больше не читается вслух с паузой посередине. `payload ui_audiobook_artifact_saved` расширен полем `joined_sentence_continuation_count` (§5.5); новых событий, уведомлений, artifact-семей и изменений retention нет — это починка, а не потеря, просматривать человеку тут нечего, и лишнее WARNING было бы шумом. Строка `narration_joined_sentence_continuation_count` появилась в summary отчёта real-document прогона тем же маршрутом, что и остальные `narration_*`.
- 2026-08-05: ревизия спеки 056 E (PR #41). Добавлено WARNING-событие `narration_omitted_paragraphs_excluded` (§3.3) и user-facing notice `result.narration_omitted_paragraphs_excluded`; `marker_paragraph_omitted` получил `omitted_source_chars`. Причина — пер-абзацное средство было тише блочного отказа, который оно заменило: оно публиковало счёт абзацев без символов и без уведомления, а мерило спеки 054 выражено в символах. Новых artifact-семей и изменений retention нет.
- 2026-08-04: спека 054 сняла с narration-проверки право ронять прогон. Добавлено WARNING-событие `narration_artifact_review_data` (§3.3), удалены `audiobook_artifact_validation_failed` и `audiobook_artifact_validation_failed_base_result_preserved` (§3.8), payload `ui_audiobook_artifact_saved` расширен полями `review_finding_count` / `review_match_count` / `review_rules` (§5.5). Новых artifact-семей и изменений retention нет: наблюдаемость обеспечивают `.run/app.log` (событие), запись о сохранённом `.run/ui_results/<stem>.result.tts.txt` и user-facing notice `result.narration_review_data` на экране результата.
- 2026-04-23: добавлен audiobook/narration contract. `.run/ui_results/` retention переведён на grouped stem pruning для `.result.md` / `.result.docx` / optional `.result.tts.txt`. Зафиксированы события `ui_audiobook_artifact_saved`, `audiobook_postprocess_chunk_started`, `audiobook_postprocess_chunk_completed` и расширенный payload `ui_result_artifacts_saved`.
