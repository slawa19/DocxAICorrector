# Контракт: события логирования и счётчики (спека 070)

Регистрирует их в `docs/LOGGING_AND_ARTIFACT_RETENTION.md` пакет WP-H (§3.3, §3.8, §5.5, новый §3.11), гард —
`_SPEC_070_LOG_EVENTS` в `tests/test_real_document_pipeline_validation.py` по образцу `_SPEC_069_LOG_EVENTS`
(`:7795-7853`: событие эмитится в `src/` И зарегистрировано в документе). Правило §1.5: полные тексты моделей в лог
не идут — только ID абзацев и образцы ≤ 120 знаков, не больше 3 на класс/причину. Новых семей артефактов `.run/` НЕТ:
всё, что нужно проверяющему, — в событиях и в отчёте раннера, который снимает их из лога (маршрут
`_extract_narration_artifact_record`, `run_lietaer_validation.py:5020`). События блочного цикла раннер пересылает в
`runs/<run_id>/events.jsonl` (спека 068 FR-002).

## Новые события

| Событие | Уровень | Где | Когда | Context |
|---|---|---|---|---|
| `audiobook_model_resolved` | DEBUG | `core/audiobook_mode.py` | при разрешении модели (UI, раннер) | `{origin, model, source}` (`source` ∈ `requested`, `config`) |
| `audiobook_narration_exclusions` | INFO | `pipeline/late_phases.py` (финализация) | один раз на прогон `audiobook`, даже при нуле | `{filename, run_id, expected_paragraph_count, excluded_count, excluded_by_reason, excluded_paragraph_ids_by_reason, fragment_samples}` |
| `audiobook_repair_started` | DEBUG | `pipeline/audiobook_repair.py` | перед вызовом | `{filename, block_index, paragraph_ids, residue_classes, model}` |
| `audiobook_repair_completed` | INFO | то же | ответ принят | `{filename, block_index, paragraph_ids, residue_before_by_class, residue_after_by_class}` |
| `audiobook_repair_failed` | WARNING | то же | отказ, ошибка или Stop | `{filename, block_index, paragraph_ids, reason, error_class, call_made}` (`reason` ∈ `marker_mismatch`, `empty_paragraph`, `error`, `stopped`) |
| `audiobook_needs_review` | WARNING | `pipeline/late_phases.py` | один раз на прогон, если есть хотя бы один абзац с пометкой | `{filename, run_id, needs_review_paragraph_count, needs_review_by_reason, records: [{paragraph_id, block_index, reasons, residue_classes, sample}]}` — `records` полный (ID + образец ≤ 120 знаков), без полных текстов |
| `audiobook_paragraph_boundary_mismatch` | ERROR | `pipeline/narration_postprocess.py` (сборка) | разбор итогового текста не совпал с записями (дефект кода; не должен случаться) | `{filename, expected_paragraph_count, delivered_paragraph_count, deterministic_join_count, parsed_paragraph_count, first_mismatch_paragraph_id}` |

## Изменённые события

| Событие | Изменение |
|---|---|
| `ui_audiobook_artifact_saved` (`late_phases.py:1628`) | поля — `data-model.md` §6; удалены `tag_count`, `mode`, `excluded_blocks`, `excluded_source_fallback_*`, `excluded_omitted_*`, `postprocess_paragraph_shortfall_*` |
| `narration_artifact_review_data` (`late_phases.py:1360`) | остаются правила `doi`, `isbn_identifier`, `arxiv_identifier`, `inline_citation`; удалены `internal_placeholder`, `raw_url`, `markdown_heading`, `disallowed_tags` (FR-006); поле `narration_mode` удалено; `match_count` — число вхождений у всех правил |
| `model_usage_accounted` (`pipeline/_pipeline.py`) | новая стадия `stages.audiobook_repair` (появляется, когда был хотя бы один ответ) |
| `config_key_ignored` (`core/config.py:1122`) | называет `audiobook_postprocess_default`, если ключ остался в пользовательском `config.toml` |

## Удалённые события (FR-002, R7)

`audiobook_postprocess_chunk_started`, `audiobook_postprocess_chunk_completed`,
`audiobook_postprocess_paragraph_shortfall`, `audiobook_postprocess_failed`,
`audiobook_postprocess_failed_base_result_preserved`, `narration_source_fallback_excluded`,
`narration_omitted_paragraphs_excluded`. В документе логирования их описания заменяются записью «удалено спекой 070» в
§3.8 и Changelog (как сделано для `audiobook_artifact_validation_failed` спекой 054); исторические прогоны не
переписываются.

## Notices экрана результата (`ui/locales/ru.json`, `en.json`, одинаковые ключи)

Новые: `result.audiobook_needs_review` (`{count}` абзацев требуют проверки; адреса — в отчёте/логе),
`result.audiobook_excluded` (`{count}` абзацев не озвучено: по причинам). Удалённые:
`result.narration_postprocess_paragraph_shortfall`, `result.narration_source_fallback_excluded*`,
`result.narration_omitted_paragraphs_excluded*`, подписи флажка `sidebar.audiobook_postprocess_label/help`.

## Отчёт раннера (`run_lietaer_validation.py`)

Секция `narration_artifact` и строки `narration_*` summary берут поля `ui_audiobook_artifact_saved` (кортеж ключей
`:5000-5017` переписывается по `data-model.md` §6) и `audiobook_narration_exclusions` / `audiobook_needs_review`;
строки цены: `model_accounting_stage_text_generation_cost_usd`, `model_accounting_stage_audiobook_repair_cost_usd`
(SC-005; если построчного вывода стадий в summary ещё нет — добавить по образцу стадии `literary_polish`).
