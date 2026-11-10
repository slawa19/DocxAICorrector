# Контракт: события логирования и поля отчёта (спека 073)

Регистрирует их в `docs/LOGGING_AND_ARTIFACT_RETENTION.md` пакет WP-I (§3.13 — новые события, §5.5 — новые поля
`ui_audiobook_artifact_saved`, `ui_result_artifacts_saved.artifact_paths`, retention `.run/ui_results/`, Changelog).
Гард — `_SPEC_073_LOG_EVENTS` и `_SPEC_073_NEW_UI_ARTIFACT_FIELDS` в `tests/test_real_document_pipeline_validation.py` по
образцу `_SPEC_072_LOG_EVENTS` (`:8036-8074`); имена начинаются с `audiobook_` — их видит сканер
`_emitted_audiobook_event_names`. Правило §1.5: полных текстов в логе нет — только ID, числа, коды причин и хвост
сообщения ≤ 300 знаков; написания сокращений и их чтения — в артефакте словаря, не в событии.
`scripts/_list_log_events.py` (`TARGETS`, `:9-51`) получает `pipeline/reading_glossary.py`.

## Новые события

| Событие | Уровень | Где | Когда | Context |
|---|---|---|---|---|
| `audiobook_reading_glossary_built` | INFO | `pipeline/reading_glossary.py` | фаза словаря завершилась статусом `built`, `partial`, `empty` или `no_candidates` | `{filename, status, call_made, candidate_count, sent_count, accepted_count, dropped_by_limit_count, rejected_by_reason, prompt_tokens, completion_tokens, cost_usd, artifact_path}` |
| `audiobook_reading_glossary_failed` | WARNING | `pipeline/reading_glossary.py` | статус `failed` (исключение клиента, ответ без JSON, нет промпта) | `{filename, reason, error_class, error_message (≤ 300), call_made, candidate_count, sent_count, artifact_path}`; `reason` ∈ `error`, `empty_response`, `no_json`, `invalid_json`, `invalid_shape`, `prompt_unavailable` |
| `audiobook_narration_minimax_failed` | WARNING | `pipeline/narration_exports.py` | `build_minimax_text` бросил исключение | `{filename, error_class, error_message (≤ 300), group_count}` |

Статус `stopped` словаря отдельного события не имеет: прогон остановлен, это видно по итогу прогона (цикл блоков,
`pipeline/block_execution.py:2614-2615`). Успешная сборка MiniMax отдельного события не имеет — факт и метки в
`ui_audiobook_artifact_saved`.

## Изменённое событие `ui_audiobook_artifact_saved` (`pipeline/late_phases.py:1578-1606`)

Все ключи 070 и 072 — без изменений. Добавляются (каждый присутствует всегда, когда событие эмитится; ноль и `null` —
утверждения):

| Ключ | Тип | Источник (research R11) | Значение |
|---|---|---|---|
| `tts_minimax_path` | `str \| null` | `event_fields` | путь `.result.tts.minimax.txt` или `null` |
| `narration_minimax_status` | `"built" \| "failed"` | `event_fields` | |
| `minimax_pause_counts` | `{chapter: int, heading: int, scene_break: int}` | `event_fields` | метки по видам (FR-007) |
| `scene_break_count` | `int` | сводка | групп с `after_scene_break` (FR-006) |
| `stress_mark_count` | `int` | сводка | U+0301 в тексте озвучки |
| `stress_marks_per_1000_words` | `float` | сводка | округление до 3 знаков |
| `latin_source_unit_count` | `int` | сводка | единиц `latin` в исходнике озвучиваемых абзацев (знаменатель SC-001) |
| `reading_glossary_status` | `str` | сводка | `data-model.md` §4 или `not_applicable` |
| `reading_glossary_candidate_count` | `int` | сводка | найдено кандидатов |
| `reading_glossary_sent_count` | `int` | сводка | отправлено (≤ 200) |
| `reading_glossary_accepted_count` | `int` | сводка | принято записей |
| `reading_glossary_dropped_by_limit_count` | `int` | сводка | отброшено пределом (их написания — в артефакте) |
| `reading_glossary_rejected_by_reason` | `dict[str, int]` | сводка | ключи `data-model.md` §4 |
| `reading_glossary_block_count` | `int` | сводка | блоков, получивших непустую секцию |
| `reading_glossary_cost_usd` | `float \| null` | сводка | цена стадии `audiobook_reading_glossary` |
| `reading_glossary_artifact_path` | `str \| null` | сводка | путь артефакта словаря |

Число единиц `latin` до/после исправления — существующие `residue_before_by_class.latin` / `residue_after_by_class.latin`
(класс добавляется сам, `pipeline/audiobook_pass.py:650-651`); отдельных ключей нет.

## Событие `ui_result_artifacts_saved`

Контекст не меняется (`{filename, artifact_paths}`); `artifact_paths` может нести `tts_minimax_path` — только когда файл
записан.

## Отчёт раннера (`tests/artifacts/real_document_pipeline/run_lietaer_validation.py`)

- `narration_artifact` — все ключи события (`_extract_narration_artifact_record`, `:5163-5185`).
- `_NARRATION_SUMMARY_FIELDS` (`:5051-5078`) += `scene_break_count`, `stress_mark_count`, `stress_marks_per_1000_words`,
  `latin_source_unit_count`, `narration_minimax_status`, `reading_glossary_status`, `reading_glossary_candidate_count`,
  `reading_glossary_sent_count`, `reading_glossary_accepted_count`, `reading_glossary_dropped_by_limit_count`,
  `reading_glossary_block_count`, `reading_glossary_cost_usd`.
- `_NARRATION_SUMMARY_JSON_FIELDS` (`:5079-5093`) += `minimax_pause_counts`, `reading_glossary_rejected_by_reason`.
- Ключ строки сводки — `narration_<поле>`, без удвоения для полей, начинающихся с `narration_` (правило 072,
  `_narration_summary_key`).
- `output_artifacts` += `tts_minimax_path`, `latest_tts_minimax_path`, `reading_glossary_path` (копия артефакта в
  каталоге прогона, `<basename>.reading_glossary.json`); строка сводки `tts_minimax_path=…` рядом с `tts_pdf_path=…`
  (`:6933-6935`); манифест `latest` — `latest_tts_minimax`.
- `_STAGE_COST_SUMMARY_STAGES` (`:5209`) += `audiobook_reading_glossary` → строка
  `model_accounting_stage_audiobook_reading_glossary_cost_usd` (`not_reported` ≠ `0`).
- Отсутствующее событие — `not_reported`, не ноль.
