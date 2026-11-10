# Контракт: события логирования и поля отчёта (спека 073)

Регистрирует их в `docs/LOGGING_AND_ARTIFACT_RETENTION.md` пакет WP-I (§3.13 — события; три события словаря уже
вписаны при слиянии WP-E, `16ccf47`; WP-I добавляет `audiobook_narration_book_failed`, §5.5 — новые поля
`ui_audiobook_artifact_saved`, `ui_result_artifacts_saved.artifact_paths`, retention `.run/ui_results/`, Changelog).
Гард — `_SPEC_073_LOG_EVENTS` и `_SPEC_073_NEW_UI_ARTIFACT_FIELDS` в `tests/test_real_document_pipeline_validation.py` по
образцу `_SPEC_072_LOG_EVENTS` (`:8036-8074`); имена начинаются с `audiobook_` — их видит сканер
`_emitted_audiobook_event_names`. Правило §1.5: полных текстов в логе нет — только ID, числа, коды причин и хвост
сообщения ≤ 300 знаков; написания сокращений и их чтения — в артефакте словаря и в файле книги, не в событии.
`scripts/_list_log_events.py` (`TARGETS`, `:9-51`) получает `pipeline/reading_glossary.py` (событие файла книги
эмитит `pipeline/narration_exports.py`, он уже в списке).

## Новые события

| Событие | Уровень | Где | Когда | Context |
|---|---|---|---|---|
| `audiobook_reading_glossary_built` | INFO | `pipeline/reading_glossary.py` | шаг словаря завершён: статус `built` или `no_candidates` | `{filename, status, candidate_count, sent_count, accepted_count, rerequested_count, unresolved_count, dropped_by_limit_count, rejected_by_reason, batch_count, call_count, retry_count, prompt_tokens, completion_tokens, cost_usd, artifact_path}` |
| `audiobook_reading_glossary_unresolved` | WARNING (`review_data=True`) | `pipeline/reading_glossary.py` | после повторного запроса у части кандидатов нет принятого чтения (`unresolved_count > 0`); шаг успешен, прогон идёт | `{filename, review_data, unresolved_count, sent_count, rejected_by_reason, artifact_path}` — написания только в артефакте |
| `audiobook_reading_glossary_failed` | ERROR (через `present_error`, как `block_failed`) | `pipeline/reading_glossary.py` | модель недоступна: пакет исчерпал попытки без разборчивого ответа или ошибка неповторяема — прогон завершается с ошибкой тем же путём, что неисправимый вызов блока (`pipeline/block_failures.py:135-243`) | `{filename, reason, batch_index, attempts, error_class, candidate_count, sent_count, artifact_path}`; `reason` ∈ `READING_UNAVAILABLE_REASONS` (`data-model.md` §4) |
| `audiobook_narration_book_failed` | WARNING | `pipeline/narration_exports.py` | `build_narration_book` бросил исключение (напр. расхождение шагов плана и групп) | `{filename, error_class, error_message (≤ 300), group_count}` |

Уровень задан событием, а не статусом (одна схема): полный ответ словаря — INFO; кандидаты без чтения после повтора —
отдельное WARNING-событие (review data); недоступность модели — ERROR и итог прогона «ошибка» (решение владельца
2026-11-10). Статусов `partial`, `empty`, `failed` нет. Повторы пакетов считаются в `retry_count` шага. Статус `stopped`
отдельного события не имеет (цикл блоков, `pipeline/block_execution.py:2614-2615`). Успешная сборка файла книги
отдельного события не имеет — факт и паузы в `ui_audiobook_artifact_saved`.

## Изменённое событие `ui_audiobook_artifact_saved` (`pipeline/late_phases.py:1578-1606`)

Все ключи 070 и 072 — без изменений. Добавляются (каждый присутствует всегда, когда событие эмитится; ноль и `null` —
утверждения):

| Ключ | Тип | Источник (research R11) | Значение |
|---|---|---|---|
| `narration_book_path` | `str \| null` | `event_fields` | путь `.result.narration.json` или `null` |
| `narration_book_status` | `"built" \| "failed"` | `event_fields` | |
| `narration_book_chapter_count` | `int` | `event_fields` | глав в файле книги (0, если не собран) |
| `narration_book_pause_counts` | `{chapter: int, heading: int, scene_break: int}` | `event_fields` | пауз по видам (FR-007) |
| `scene_break_count` | `int` | сводка | групп с `after_scene_break` (FR-006) |
| `stress_mark_count` | `int` | сводка | U+0301 в тексте озвучки |
| `stress_marks_per_1000_words` | `float` | сводка | округление до 3 знаков |
| `latin_source_unit_count` | `int` | сводка | единиц `latin` в исходнике озвучиваемых абзацев (знаменатель SC-001) |
| `reading_glossary_status` | `str` | сводка | `built` / `no_candidates` / `stopped` или `not_applicable` |
| `reading_glossary_candidate_count` | `int` | сводка | найдено кандидатов |
| `reading_glossary_sent_count` | `int` | сводка | отправлено (≤ 200) |
| `reading_glossary_accepted_count` | `int` | сводка | принято записей |
| `reading_glossary_rerequested_count` | `int` | сводка | ушло в повторный запрос |
| `reading_glossary_unresolved_count` | `int` | сводка | без чтения и после повтора (SC-010: 0) |
| `reading_glossary_dropped_by_limit_count` | `int` | сводка | отброшено пределом (их написания — в артефакте) |
| `reading_glossary_rejected_by_reason` | `dict[str, int]` | сводка | ключи `READING_REJECTION_REASONS` |
| `reading_glossary_batch_count` | `int` | сводка | пакетов обоих проходов |
| `reading_glossary_call_count` | `int` | сводка | вызовов модели шага, включая повторы |
| `reading_glossary_retry_count` | `int` | сводка | повторов пакетов |
| `reading_glossary_block_count` | `int` | сводка | блоков, получивших непустую секцию |
| `reading_glossary_cost_usd` | `float \| null` | сводка | цена стадии `audiobook_reading_glossary` |
| `reading_glossary_artifact_path` | `str \| null` | сводка | путь артефакта словаря |

Число единиц `latin` до/после исправления — существующие `residue_before_by_class.latin` / `residue_after_by_class.latin`
(класс добавляется сам, `pipeline/audiobook_pass.py:650-651`); отдельных ключей нет. При падении шага словаря событие не
эмитится (прогон не доходит до позднего этапа) — как при неисправимом сбое блока.

## Событие `ui_result_artifacts_saved`

Контекст не меняется (`{filename, artifact_paths}`); `artifact_paths` может нести `narration_book_path` — только когда
файл записан.

## Отчёт раннера (`tests/artifacts/real_document_pipeline/run_lietaer_validation.py`)

- `narration_artifact` — все ключи события (`_extract_narration_artifact_record`, `:5163-5185`).
- `_NARRATION_SUMMARY_FIELDS` (`:5051-5078`) += `scene_break_count`, `stress_mark_count`, `stress_marks_per_1000_words`,
  `latin_source_unit_count`, `narration_book_status`, `narration_book_chapter_count`, `reading_glossary_status`,
  `reading_glossary_candidate_count`, `reading_glossary_sent_count`, `reading_glossary_accepted_count`,
  `reading_glossary_rerequested_count`, `reading_glossary_unresolved_count`, `reading_glossary_dropped_by_limit_count`,
  `reading_glossary_batch_count`, `reading_glossary_call_count`, `reading_glossary_retry_count`,
  `reading_glossary_block_count`, `reading_glossary_cost_usd`.
- `_NARRATION_SUMMARY_JSON_FIELDS` (`:5079-5093`) += `narration_book_pause_counts`, `reading_glossary_rejected_by_reason`.
- Ключ строки сводки — `narration_<поле>`, без удвоения для полей, начинающихся с `narration_` (правило 072,
  `_narration_summary_key`): `narration_book_status=…`, не `narration_narration_book_status`.
- `output_artifacts` += `narration_book_path`, `latest_narration_book_path`, `narration_book_valid_json`,
  `narration_book_schema_version`, `narration_book_segments_equal_tts`, `narration_book_chapter_count` (проверка файла
  раннером: открыть JSON, сравнить `"\n\n".join(text)` с `.tts.txt` прогона), `reading_glossary_path` (копия артефакта в
  каталоге прогона, `<basename>.reading_glossary.json`; путь — из `audiobook_reading_glossary_built` или, при падении
  шага, из `audiobook_reading_glossary_failed`); строка сводки `narration_book_path=…` рядом с `tts_pdf_path=…`
  (`:6933-6935`); манифест `latest` — `latest_narration_book`.
- `_STAGE_COST_SUMMARY_STAGES` (`:5209`) += `audiobook_reading_glossary` → строка
  `model_accounting_stage_audiobook_reading_glossary_cost_usd` (`not_reported` ≠ `0`).
- Отсутствующее событие — `not_reported`, не ноль.
