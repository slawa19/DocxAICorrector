# Data Model: P2 спеки 063 — глоссарий прогона

## GlossarySourceUnit (новая, `text/glossary_pass.py`)

Один абзац, из которого извлекаются кандидаты.

- `unit_id: str` — `paragraph_id` абзаца;
- `text: str` — `ParagraphUnit.text` (с разметкой `*курсив*` / `**полужирный**`, как у импорта);
- `is_heading: bool` — роль `heading`: в счёт вхождений идёт, в серии имён — нет (в заголовках
  все слова прописные, это не сигнал имени).

Отбор (`select_glossary_source_units(jobs, source_paragraphs)`): абзацы `llm`-заданий, у которых
регион ∈ {`prose`, `front_matter`}; порядок — порядок документа; изображения и пустые абзацы
пропускаются. Если у задания нет `paragraph_regions` (старые двойники), абзац берётся как `prose`.

## GlossaryCandidate (новая)

- `source_term: str` — поверхностная форма первого найденного вхождения;
- `key: tuple[str, ...]` — нормированные слова (множественное число свёрнуто; у имён регистр
  сохранён, у прочих — нижний);
- `family: str` ∈ {`marked`, `name`, `collocation`, `head`};
- `signals: tuple[str, ...]` — подмножество {`emphasis`, `quoted`, `defined`, `capitalised`,
  `collocation`, `family_head`};
- `occurrence_count: int`, `unit_count: int` (≥ 2 — иначе не кандидат), `spread: int` (сколько
  десятых долей книги покрыто);
- `first_unit_id: str`, `context: str` (≤ 100 символов вокруг первого вхождения, без разметки);
- `score: float` — ранг внутри семейства.

Инварианты: ни одного литерала книги в коде; `unit_count ≥ 2`; длина ≤ 4 слов; одно слово —
не короче 2 букв; кандидаты уникальны по `key` без учёта регистра.

## GlossaryTerm (существующая, `document/segments.py:77-81` — расширяется)

Сегодня: `source_term`, `target_term`, `confidence="medium"`, `source_segment_id=None`.

Добавляются (с умолчаниями, поэтому все сегодняшние конструкторы работают):

- `kind: str = "term"` — `term` | `name` (FR-015: имена собственные — тем же глоссарием);
- `note: str = ""` — условие или пояснение (FR-013: два смысла → две записи, различаются `note`).

Рендер строки: `- {source_term} -> {target_term}`, затем ` (имя)` для `kind == "name"`, затем
` — {note}`, если `note` не пуст. Префикс `source -> target` прежний — на нём стоят сегодняшние
тесты (`tests/test_app.py:52`, `tests/test_processing_service.py:353`).

## RunGlossary (новая, итог фазы)

- `status: str` ∈ {`built`, `empty`, `failed`, `stopped`, `no_candidates`};
- `terms: tuple[GlossaryTerm, ...]` — принятые записи, порядок ответа модели;
- `candidate_count: int`, `request_candidate_count: int` (после снятия доменных терминов);
- `rejected_counts: dict[str, int]` — `not_a_candidate`, `empty_target`, `duplicate_sense`,
  `over_limit`;
- `domain_term_count: int` — сколько терминов дал доменный вход (FR-016);
- `prompt_section_chars: int`, `rendered_term_count: int` — сколько вошло в бюджет;
- `model: str`, `usage: dict` — `prompt_tokens`, `completion_tokens`, `cost_usd` из стадии
  `glossary_extraction` учёта прогона (`None`, если провайдер не сообщил);
- `error_code: str | None`, `artifact_path: str | None`.

Переходы: `not_applicable` (операция не `translate` или ключ выключен) — фаза не запускается и
ничего не пишет; `no_candidates` — вызова нет; `stopped` — «Стоп» до вызова; `built` — ≥ 1 запись;
`empty` — модель ответила валидно, но ни одной записи не принято; `failed` — исключение или
невалидный ответ. Только `built` меняет промпт.

## ProcessingState (существующая, `pipeline/contracts.py:257`)

- `run_glossary_status: str = "not_applicable"` и `run_glossary_term_count: int = 0` — нужны
  `late_phases` для уведомления; сам глоссарий в состоянии не хранится (он в промпте и в артефакте).

## Конфиг (ключи `app_config`)

| ключ | тип | по умолчанию в `config.toml` | env | если ключа нет в `app_config` |
|---|---|---|---|---|
| `glossary_pass_enabled` | bool | `true` | `DOCX_AI_GLOSSARY_PASS_ENABLED` | `False` |
| `glossary_max_terms` | int, 0…200 | `60` | `DOCX_AI_GLOSSARY_MAX_TERMS` | `60` |
| `glossary_prompt_max_chars` | int, 0…20000 | `3000` | `DOCX_AI_GLOSSARY_PROMPT_MAX_CHARS` | `3000` |
| `glossary_candidate_limit` | int, 20…1000 | `400` | `DOCX_AI_GLOSSARY_CANDIDATE_LIMIT` | `400` |

`False` при отсутствии ключа — намеренно: `app_config`, собранный руками (тесты, сторонний
вызывающий), не знает о проходе и не должен незаметно получить платный вызов; загрузчик конфига
всегда кладёт ключ, поэтому продукт по умолчанию — включено.
