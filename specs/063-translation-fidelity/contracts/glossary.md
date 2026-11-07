# Contract: глоссарий прогона (спека 063, P2)

## Применимость

- Фаза запускается, только если `context.processing_operation == "translate"` и
  `app_config["glossary_pass_enabled"]` истинно, и в плане есть хотя бы одно `llm`-задание.
- Иначе фаза не делает ничего: ни вызова, ни события, ни артефакта, промпт не меняется.

## Вход вызова

Один запрос через текстовый клиент и модель прогона (`initialization.text_client`,
`initialization.text_model_id`), стадия учёта `glossary_extraction`:

- системная инструкция — `resources/prompts/glossary_extraction.txt` (языки подставляются);
- пользовательская часть — JSON: `source_language`, `target_language`, `max_terms`,
  `fixed_terms` (доменный вход FR-016: `[{source_term, target_term}]`), `candidates`
  (`[{id, term, family, count, context}]`);
- `temperature = 0.2`, `max_output_tokens` — по `max_terms` (≈ 60 токенов на запись, не меньше
  1 024, не больше 8 192).

## Ответ модели

```json
{"terms": [{"source_term": "bank-debt money", "target_term": "банковские долговые деньги",
            "kind": "term", "note": ""}]}
```

Правила приёма (каждое отказное правило считается в `rejected_counts`):

- `source_term` совпадает с кандидатом запроса после той же нормировки (`not_a_candidate`);
- `target_term` — непустая строка (`empty_target`);
- `kind` ∈ {`term`, `name`}, иное → `term`;
- не больше двух записей на один `source_term`, и вторая — только с непустым `note`, отличным от
  первой (`duplicate_sense`);
- не больше `glossary_max_terms` записей (`over_limit`).

## Выход в промпт

- Принятые записи рендерятся `render_glossary_prompt_section(terms, header=…, max_chars=…)`
  (`document/segments.py`) в раздел:

  ```text
  ГЛОССАРИЙ ЭТОЙ КНИГИ (построен по документу для текущего запуска; передавайте эти термины и
  имена так во всех блоках, склоняя по-русски, если не сказано иное):
  - bank-debt money -> банковские долговые деньги
  - Lietaer -> Лиетар (имя)
  - value -> стоимость — в значении экономической категории
  ```

- раздел дописывается к `context.document_context_prompt` через `dataclasses.replace`; строки
  идут по порядку, пока помещаются в `glossary_prompt_max_chars`; не поместилось — «- …»;
- статусы, кроме `built`, промпт не меняют.

## Артефакт

`.run/run_glossaries/<run_id|source_token|"run">_<epoch_ms>.json`, атомарная запись, после записи
— `prune_artifact_dir(max_age=14 дней, max_count=200)`:

```json
{"schema": "run_glossary/v1", "run_id": "…", "source_token": "…", "filename": "…",
 "status": "built", "model": "…", "source_language": "en", "target_language": "ru",
 "candidate_count": 398, "request_candidate_count": 398, "domain_term_count": 0,
 "terms": [{"source_term": "…", "target_term": "…", "kind": "term", "note": ""}],
 "rejected_counts": {"not_a_candidate": 0, "empty_target": 0, "duplicate_sense": 0, "over_limit": 0},
 "rendered_term_count": 52, "prompt_section_chars": 2987,
 "usage": {"prompt_tokens": 13210, "completion_tokens": 2104, "cost_usd": 0.0065},
 "candidates": [{"term": "…", "family": "name", "signals": ["capitalised"], "count": 36,
                 "unit_count": 30, "spread": 5, "first_unit_id": "p0961", "context": "…"}],
 "error_code": null}
```

Сбой записи артефакта — WARNING `run_glossary_artifact_write_failed`, прогон и промпт не
затронуты, `artifact_path = null`.

## События (`docs/LOGGING_AND_ARTIFACT_RETENTION.md` §3.3)

- `run_glossary_built` — INFO, один раз на прогон, для `built`, `empty`, `no_candidates`.
  Context: `{filename, status, model, candidate_count, request_candidate_count, domain_term_count,
  term_count, rendered_term_count, prompt_section_chars, rejected_counts, prompt_tokens,
  completion_tokens, cost_usd, artifact_path}`. Сами термины в лог не идут (§1.5) — они в
  артефакте.
- `run_glossary_failed` — WARNING, для `failed`. Context: `{filename, status, model, error_code,
  error_message (≤ 120 символов), candidate_count, artifact_path}`.
- `stopped` — без отдельного события: остановку прогона уже сообщают свои события.

## Отчёт real-document прогона и summary

- `report["run_glossary"]` — содержимое артефакта (если путь из события читается) или контекст
  события; `None`, если события не было (операция не `translate` или проход выключен).
- Summary: `run_glossary_status`, `run_glossary_term_count`, `run_glossary_rendered_term_count`,
  `run_glossary_candidate_count`, `run_glossary_prompt_section_chars`,
  `run_glossary_prompt_tokens`, `run_glossary_completion_tokens`, `run_glossary_cost_usd`,
  `run_glossary_terms` (JSON-список строк `source -> target`), `run_glossary_artifact`; без
  события — одна строка `run_glossary=not_reported`.

## UI

- Канал — существующий `latest_result_notices`; новый вид `glossary` в
  `_RENDERED_RESULT_NOTICE_KINDS` (`ui/_ui.py:753`).
- `built` → `{"kind": "glossary", "level": "info", "message_key": "result.run_glossary_built",
  "params": {"count": N}}`; `failed` → `level: "warning"`, `message_key:
  "result.run_glossary_failed"`, без параметров. Остальные статусы — без уведомления.
- Ключи есть в `ui/locales/ru.json` и `en.json`.

## Не-гейт

Ни один статус глоссария не меняет `delivery_disposition`, `quality_status`, приёмочный вердикт
или код выхода раннера.
