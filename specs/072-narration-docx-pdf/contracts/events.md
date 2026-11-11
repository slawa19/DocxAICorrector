# Контракт: события логирования и поля отчёта (спека 072)

Регистрирует их в `docs/LOGGING_AND_ARTIFACT_RETENTION.md` пакет WP-I (§3.11 — новые события, §5.5 — поля
`ui_audiobook_artifact_saved`, retention `.run/ui_results/`, Changelog). Гард — `_SPEC_072_LOG_EVENTS` в
`tests/test_real_document_pipeline_validation.py` по образцу `_SPEC_070_LOG_EVENTS` (`:7912-7979`: событие эмитится в
`src/` И зарегистрировано в документе); имена начинаются с `audiobook_`, поэтому их видит и сканер
`_emitted_audiobook_event_names` (`:7948-7959`). Правило §1.5: полные тексты не идут в лог — только ID абзацев, числа,
коды причин и хвост stderr ≤ 300 знаков. `scripts/_list_log_events.py` получает новые модули
`pipeline/narration_exports.py`, `generation/narration_pdf.py` (список `TARGETS`, `:9-45`).

## Новые события

| Событие | Уровень | Где | Когда | Context |
|---|---|---|---|---|
| `audiobook_narration_docx_failed` | ERROR | `pipeline/narration_exports.py` | рендерер DOCX бросил исключение (напр. `ValueError` на символе, недопустимом в XML) | `{filename, error_class, error_message (≤ 300), group_count}` |
| `audiobook_narration_pdf_unavailable` | WARNING | `pipeline/narration_exports.py` | PDF не собран по любой причине, включая `docx_not_built` | `{filename, reason, seconds, detail (≤ 300), timeout_seconds}`; `reason` ∈ `data-model.md` §4 |
| `audiobook_studio_limits_exceeded` | WARNING (`review_data=True`, `advisory=True`) | `pipeline/narration_exports.py` | хотя бы один лимит FR-006 превышен (строго больше) | `{filename, exceeded, heading1_count, max_chapter_paragraph_count, max_paragraph_chars, limits: {chapters: 500, chapter_paragraphs: 400, paragraph_chars: 5000}}` |

Успешный экспорт отдельного события не имеет: факт и время — в `ui_audiobook_artifact_saved` (ниже).

## Изменённое событие `ui_audiobook_artifact_saved` (`pipeline/late_phases.py:1544-1565`)

Все прежние ключи (спека 070, `data-model.md` §6 и `docs/LOGGING_AND_ARTIFACT_RETENTION.md:416`) — без изменений.
Добавляются (каждый ключ присутствует всегда; ноль и `null` — утверждения):

| Ключ | Тип | Значение |
|---|---|---|
| `tts_docx_path` | `str \| null` | путь `.result.tts.docx` или `null`, если DOCX не собран |
| `tts_pdf_path` | `str \| null` | путь `.result.tts.pdf` или `null` |
| `narration_docx_status` | `"built" \| "failed"` | |
| `narration_pdf_status` | `"built" \| "unavailable"` | |
| `narration_pdf_unavailable_reason` | `str \| null` | код `data-model.md` §4 |
| `narration_pdf_seconds` | `float` | стена конвертации, `0.0` если не запускалась |
| `chapter_heading_level` | `int \| null` | уровень главы — порог: `Heading 1` получают серии этого уровня и выше (FR-003 (а) в редакции спеки 074 FR-101…FR-103: самый верхний уровень, при котором ни одна глава не длиннее 400 абзацев) |
| `heading_levels_present` | `list[int]` | различные уровни заголовков среди озвучиваемых групп |
| `heading1_count` | `int` | число `Heading 1` = ожидаемое число глав Studio |
| `demoted_heading_count` | `int` | абзацев из заголовков глубже уровня главы, записанных `Normal` |
| `heading_merge_count` | `int` | серий из ≥ 2 заголовков |
| `heading_merges` | `list[{paragraph_ids: list[str], levels: list[int], style: str}]` | все слияния FR-003 (в); тексты не пишутся |
| `studio_max_chapter_paragraph_count` | `int` | FR-006 |
| `studio_max_paragraph_chars` | `int` | FR-006 |
| `studio_limits_exceeded` | `list[str]` | `[]` или подмножество `chapters`, `chapter_paragraphs`, `paragraph_chars` |
| `narration_docx_paragraph_count` | `int` | абзацев в `.tts.docx` (после слияний) |

Событие по-прежнему эмитится, только когда сохранён `.tts.txt` (`"tts_text_path" in result_artifact_paths`, `:1544`);
при сбое DOCX/PDF — с `null`-путями и причиной.

## Событие `ui_result_artifacts_saved`

Контекст не меняется (`{filename, artifact_paths}`); `artifact_paths` теперь может нести `tts_docx_path`,
`tts_pdf_path` (`data-model.md` §6).

## Notices экрана результата (`ui/locales/ru.json`, `en.json`, одинаковые ключи)

| Ключ | Уровень | Параметры | Когда |
|---|---|---|---|
| `result.audiobook_studio_limits_exceeded` | warning | `{limits}` — перечисление превышенных лимитов с числами | превышен хотя бы один лимит FR-006 |

Отсутствие PDF/DOCX — не notice, а строка экрана у кнопок по причине из bundle (`contracts/state-bundle.md`).

## Отчёт раннера (`tests/artifacts/real_document_pipeline/run_lietaer_validation.py`)

- `narration_artifact` (секция отчёта) — все ключи события, как сейчас (`_extract_narration_artifact_record`,
  `:5052-5072`).
- `_NARRATION_SUMMARY_FIELDS` (`:5011-5028`) += `heading1_count`, `heading_merge_count`, `demoted_heading_count`,
  `studio_max_chapter_paragraph_count`, `studio_max_paragraph_chars`, `narration_docx_status`,
  `narration_pdf_status`, `narration_pdf_seconds`, `narration_docx_paragraph_count`.
- `_NARRATION_SUMMARY_JSON_FIELDS` (`:5029-5039`) += `heading_merges`, `heading_levels_present`,
  `studio_limits_exceeded`, `narration_pdf_unavailable_reason`.
- `output_artifacts` += `tts_docx_path`, `tts_pdf_path`, `latest_tts_docx_path`, `latest_tts_pdf_path`,
  `tts_docx_openable`, `tts_docx_paragraphs`, `tts_docx_heading1_count`, `tts_docx_other_heading_style_count`; строки
  сводки `tts_docx_path=…`, `tts_pdf_path=…` рядом с `tts_text_path=…` (`:6798`); манифест `latest` —
  `latest_tts_docx`, `latest_tts_pdf` (`_write_latest_aliases`, `:1595-1632`).
- Ключ строки сводки — `narration_<поле>`; поле, чьё имя в событии уже начинается с `narration_`, сохраняет имя как
  есть, без удвоения: `narration_docx_status=…`, `narration_pdf_status=…`, `narration_pdf_seconds=…`,
  `narration_docx_paragraph_count=…`, `narration_pdf_unavailable_reason=…` (не `narration_narration_…`);
  остальные поля — `narration_heading1_count=…` и т. д. (`_narration_summary_key`).
- Отсутствующее событие — `not_reported`, не ноль (как сейчас).
