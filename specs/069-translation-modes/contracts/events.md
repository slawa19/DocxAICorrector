# Контракт: новые и изменённые события логирования

Регистрирует их в `docs/LOGGING_AND_ARTIFACT_RETENTION.md` пакет WP-9 (§3, §5.1). Правило §1.5: полные тексты
моделей в лог не идут — только в артефакты. События блочного цикла раннер пересылает в `runs/<run_id>/app.log` и
`events.jsonl` (спека 068 FR-002).

| Событие | Уровень | Где эмитится | Context |
|---|---|---|---|
| `translation_modes_resolved` | DEBUG | `core/translation_modes.py` при загрузке | `{default_mode, modes: {name: {model, editorial_intensity, reasoning_effort, polish_model, polish_reasoning_effort}}, sources: {key: "toml"\|"env"}}` |
| `translation_mode_overrides_setting` | WARNING | `resolve_effective_translation_config` | `{origin, mode, overridden: [{field, requested, effective}]}` |
| `translation_mode_ignored_for_operation` | WARNING | то же | `{origin, processing_operation, translation_mode}` |
| `model_call_param_dropped` (существует) | WARNING | `image/shared.py::drop_rejected_optional_param` | + `param="reasoning"`, + `nested_in` (`null` \| `"extra_body"`) |
| `reasoning_effort_not_supported_for_provider` | WARNING, раз на (модель, уровень) в процессе | `generation/_generation.py` (Anthropic) | `{provider, model, reasoning_effort, stage}` |
| `literary_polish_paragraph_rolled_back` | WARNING | `pipeline/literary_polish.py` | `{filename, run_id, block_index, paragraph_id, polish_model, reasons, details_summary, artifact_path}` (без текстов) |
| `literary_polish_block_failed` | WARNING | то же | `{filename, run_id, block_index, polish_model, reason: "error"\|"empty"\|"block_marker_mismatch"\|"stopped", error_class, paragraph_count, artifact_path}` |
| `literary_polish_completed` | INFO, раз на прогон | то же, из финализации блоков | `{filename, run_id, polish_model, sent_block_count, sent_paragraph_count, accepted_paragraph_count, rolled_back_paragraph_count, rollback_reason_counts, block_rollback_count, failed_block_count, skipped_paragraph_counts, artifact_path}` |
| `literary_polish_artifact_write_failed` | WARNING | то же | `{run_id, path, error_class}` |
| `price_list_fetch_failed` | WARNING | `pipeline/price_list.py` | `{source_url, error_class, cache_fetched_at}` |
| `cost_estimate_computed` | DEBUG | `ui/_app.py`, раннер | `{source_token, coefficients_version, price_list_date, modes: {name: {upper, lower}}}` |
| `cost_estimate_vs_actual` | INFO, раз на прогон | `pipeline/_pipeline.py` рядом с `model_usage_accounted` (`:1167`) | `{filename, run_id, mode, coefficients_version, price_list_date, stages: {s: {estimate_upper, estimate_lower, actual}}, estimate_upper_usd, estimate_lower_usd, actual_usd, relative_error_vs_upper, within_range, run_complete, cost_accounting_complete}` |
| `model_usage_accounted` (существует) | INFO | `pipeline/_pipeline.py:1170` | `stages.*` получают поля рассуждения и кеша; новый раздел `literary_polish` (счётчики второго прохода) |

Семьи артефактов `.run/` (§5.1):

| Путь | Срок / число | Писатель |
|---|---|---|
| `.run/literary_polish_rollbacks/<run_id>.jsonl` | 7 дней / 400 файлов, `prune_artifact_dir` после записи | `pipeline/literary_polish.py` |
| `.run/price_list/openrouter_models.json` | один файл, перезапись; без срока | `pipeline/price_list.py` |
| `runs/<run_id>/literary_polish_rollbacks.jsonl` | как каталог прогона | раннер (копия) |
