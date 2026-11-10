# Data Model: текст для озвучки, который голос читает без ошибок

**Spec**: [spec.md](spec.md) | **Plan**: [plan.md](plan.md) | **Research**: [research.md](research.md)

Сущности новые или меняющиеся. Пути — относительно `src/docxaicorrector/`; ссылки сверены на `7347bd3`. Словари
значений ЗАКРЫТЫ: неизвестное значение — ошибка теста, не молчаливое «прочее». Полные тексты в лог не идут
(LOGGING §1.5): в событиях — ID, числа и коды причин; написания сокращений и их чтения — только в артефакте словаря.

## 1. Формы текста: знаки и серии (FR-002, FR-003, FR-004; research R1)

`text/narration_forms.py` (новый, лист — импортирует только `re`, `unicodedata`, `dataclasses`):

```text
without_combining_marks(text: str) -> str
    символы категории M* удалены (перенос document/narration_exclusion.py:93-96 дословно)

without_combining_marks_with_offsets(text: str) -> tuple[str, tuple[int, ...]]
    (stripped, offsets): offsets[i] — индекс stripped[i] в text; len(offsets) == len(stripped)

original_span(text: str, offsets, start: int, end: int) -> tuple[int, int]
    спан [start, end) строки без знаков → спан исходной строки; конец продлевается через следующие M*

LetterSeries(frozen): text: str, start: int, end: int        # позиции — исходной строки

letter_series(text: str, *, digits_inside: bool = False) -> tuple[LetterSeries, ...]
    максимальная серия символов: L* | M* | "-" U+2010 U+2011 | "'" U+2019 | (Nd, если digits_inside);
    дефисы и апострофы по краям отрезаются; серия без буквы L* — не единица
```

Инвариант: `without_combining_marks(t) == t` для текста без знаков (тест на корпусе синтетики); `letter_series`
не делит слово на знаке ударения (`за́мок` — одна единица).

## 2. Класс остатка `latin` (FR-003; research R2)

`text/narration_residue.py`:

```text
RESIDUE_LATIN = "latin"
RESIDUE_CLASSES = (digits, roman_numerals, symbols, all_caps, url_or_domain, tag_form, latin, html_left, emoji_left)
REPAIRABLE_RESIDUE_CLASSES = {digits, roman_numerals, symbols, all_caps, url_or_domain, tag_form, latin}

latin_units(text: str) -> tuple[LetterSeries, ...]
    спаны _URL_OR_DOMAIN заменены пробелами той же длины → letter_series(…, digits_inside=False) →
    единицы, где есть буква с "LATIN" в unicodedata.name, кроме единиц целиком формы roman_numerals
    (≥ 2 из [IVXLCDM] или все символы Nl)
```

`detect_narration_residue` добавляет `ResidueFinding("latin", count=len(units), sample=_sample(text, units[0].start))`.
`all_caps` и `roman_numerals` ищут по `without_combining_marks_with_offsets(text)`; позиция образца — исходной строки.

## 3. Запись озвучки и сводка (FR-010; research R11)

`pipeline/audiobook_pass.py`:

```text
NarrationParagraphRecord(frozen)          # :116-130, поле ПОСЛЕДНИМ
    ...существующие поля без изменений...
    source_latin_unit_count: int = 0      # len(latin_units(item.source_text)); 0 у неадресуемой записи без исходника

audiobook_narration_summary(state) -> dict   # :617-672, новые ключи (всегда присутствуют):
    stress_mark_count: int                    # число U+0301 во всех record.text
    stress_marks_per_1000_words: float        # round(count * 1000 / max(1, слов), 3); слова — [^\W\d_]+ по тексту без знаков
    latin_source_unit_count: int              # сумма record.source_latin_unit_count
    scene_break_count: int                    # групп state.narration_groups с after_scene_break
    reading_glossary_status: str              # §4 ReadingGlossary.status; "not_applicable", если словаря нет
    reading_glossary_candidate_count: int
    reading_glossary_sent_count: int
    reading_glossary_accepted_count: int
    reading_glossary_dropped_by_limit_count: int
    reading_glossary_rejected_by_reason: dict[str, int]
    reading_glossary_block_count: int         # len(state.audiobook_reading_glossary_block_indexes)
    reading_glossary_cost_usd: float | None
    reading_glossary_artifact_path: str | None
```

## 4. Словарь чтения (FR-004; research R4–R7)

`pipeline/reading_glossary.py` (новый):

```text
READING_GLOSSARY_MAX_CANDIDATES = 200
READING_GLOSSARY_CONTEXT_CHARS = 160
READING_GLOSSARY_SECTION_MAX_CHARS = 2000
READING_GLOSSARY_SECTION_HEADER = <литерал contracts/prompt-and-glossary.md §2>
READING_GLOSSARY_SCHEMA = "audiobook_reading_glossary/v1"

READING_GLOSSARY_STATUSES = ("built", "partial", "no_candidates", "empty", "failed", "stopped")
    built         — вызов сделан, принята хотя бы одна запись и отказов нет
    partial       — принята хотя бы одна запись, есть отказы или кандидаты без ответа
    no_candidates — кандидатов нет, вызова нет
    empty         — вызов сделан, принятых записей 0 (ответ разобран)
    failed        — исключение клиента / неразборчивый ответ (коды _load_json_object) / нет промпта
    stopped       — Stop до или во время вызова
READING_REJECTION_REASONS = ("not_a_candidate", "empty_reading", "latin_in_reading", "digit_in_reading", "duplicate")

ReadingParagraph(frozen): paragraph_id: str, block_index: int, text: str    # исходник озвучиваемого абзаца

ReadingCandidate(frozen)
    abbreviation: str          # точное написание единицы
    occurrences: int
    first_block_index: int
    context: str               # ≤ READING_GLOSSARY_CONTEXT_CHARS вокруг первого вхождения; только в запрос
    sent: bool                 # False — отброшен пределом

ReadingEntry(frozen): abbreviation: str, reading: str

ReadingGlossary(frozen)
    status: str                             # READING_GLOSSARY_STATUSES
    candidates: tuple[ReadingCandidate, ...]
    entries: tuple[ReadingEntry, ...]       # принятые, порядок ответа
    rejected_by_reason: Mapping[str, int]
    call_made: bool
    prompt_tokens: int | None; completion_tokens: int | None; cost_usd: float | None
    artifact_path: str | None
    error_class: str | None
    def entry_for(abbreviation) -> ReadingEntry | None

reading_candidate_units(text: str) -> tuple[str, ...]
    пусто, если абзац целиком заглавными (форма all_caps); иначе letter_series(…, digits_inside=True) с маской
    адресов, где заглавных ≥ 2 и заглавных > строчных, кроме формы roman_numerals

extract_reading_candidates(paragraphs) -> tuple[ReadingCandidate, ...]
    по всем абзацам; частота desc, затем первое появление; первые MAX — sent=True

run_reading_glossary(*, paragraphs, client, model_id, should_stop, log_event, filename, artifact_context,
                     request_text_completion_fn=request_text_completion,
                     write_artifact_fn=_write_run_glossary_artifact) -> ReadingGlossary
    ровно 0 или 1 вызов request_text_completion_fn(_single_attempt_client(client), request,
    usage_stage=STAGE_AUDIOBOOK_READING_GLOSSARY, should_stop=should_stop); не бросает (кроме BaseException)

parse_reading_glossary_response(raw_text, *, sent: Sequence[ReadingCandidate]) -> tuple[entries, rejected_by_reason]
    _load_json_object; список "readings"; запись принимается, если abbreviation побайтно равно отправленному,
    reading непуст после strip, без буквы LATIN и без цифры Nd, и abbreviation ещё не принят

reading_section_for_block(glossary: ReadingGlossary | None, source_texts: Sequence[str]) -> str
    кандидатные единицы исходника по порядку первого появления ∩ glossary.entries →
    render_glossary_prompt_section([GlossaryTerm(source_term=a, target_term=r)], header=HEADER, max_chars=2000); иначе ""

run_reading_glossary_phase(*, context, dependencies, emitters, state, initialization) -> None
    только операция audiobook: абзацы из context.jobs (ID, narration_exclusion_reasons is None, _block_source_texts)
    → run_reading_glossary → state.audiobook_reading_glossary
```

Артефакт (`.run/run_glossaries/<run>_<ms>.json`, пишется, если вызов сделан):

```text
{schema: "audiobook_reading_glossary/v1", filename, run_id, model, status,
 candidates: [{abbreviation, occurrences, sent}], readings: [{abbreviation, reading}],
 rejected_by_reason: {...}, usage: {prompt_tokens, completion_tokens, cost_usd}}
```

Изоляция (Anti-regression 6): словарь живёт в `ProcessingState` этого прогона и в артефакте с его `run_id`; модуль не
держит состояния между прогонами (`lru_cache` — только у загрузчика промпта).

## 5. Состояние прогона (`pipeline/contracts.py`, объявления — один пакет)

```text
ProcessingState                                                     # :260-312
    narration_paragraph_kinds: list[tuple[str, str]] = field(default_factory=list)   # (paragraph_id, kind)
    audiobook_reading_glossary: Any = None                                           # ReadingGlossary | None
    audiobook_reading_glossary_block_indexes: set[int] = field(default_factory=set)

NARRATION_PARAGRAPH_KINDS = ("narrated", "scene_break", "excluded")   # закрытый словарь (pipeline/audiobook_pass.py)

ResultArtifactWriter.__call__(..., narration_minimax_text: str | None = None)        # :151-166, последним
```

## 6. Отметка разделителя и группа (FR-006; research R8)

`document/narration_exclusion.py`:

```text
has_no_letter_or_digit(text) -> bool        # not any(c.isalnum() for c in text); вызывается и ветвью :161-167
is_scene_break_text(text) -> bool           # text.strip() != "" and has_no_letter_or_digit(text)
```

`pipeline/narration_postprocess.py`:

```text
NarrationGroup(frozen)                      # :101-114
    paragraph_ids, role, heading_level, text      # без изменений
    after_scene_break: bool = False               # новое, последним

scene_break_before_ids(kinds: Sequence[tuple[str, str]], *, present_ids: Collection[str]) -> frozenset[str]

assemble_narration_records(records, expected_paragraph_ids=None, scene_break_before_ids=frozenset())
    склейка body+body запрещена, если ID следующей записи в множестве
```

Таблица примеров (SC-006, обязательна в тестах; `B` — тело, `H` — заголовок, `*` — разделитель, `x` — иное исключение):

| Последовательность видов | Отметки (ID получателя) | Склейка `B1+B2` возможна? |
|---|---|---|
| `B1 * B2` | `B2` | нет |
| `B1 * * B2` | `B2` (одна) | нет |
| `B1 * x B2` | `B2` | нет |
| `B1 x B2` | — | да (как сейчас) |
| `* B1 B2` (начало книги) | — | да |
| `B1 B2 *` (конец книги) | — | да |
| `H1 * B1` | `B1` | — (заголовок не склеивается) |
| `B1 *` / конец блока, `B2` — первый абзац следующего блока | `B2` | нет |
| `B1 * B2`, у `B2` пустой текст, затем `B3` | `B3` | — |

## 7. Текст для MiniMax (FR-007; research R9)

`pipeline/narration_minimax.py` (новый, чистый):

```text
MINIMAX_PAUSE_CHAPTER = "<#1.5#>"; MINIMAX_PAUSE_HEADING = "<#0.8#>"; MINIMAX_PAUSE_SCENE_BREAK = "<#2.0#>"
MINIMAX_PAUSE_KINDS = ("chapter", "heading", "scene_break")      # приоритет при совпадении — по длительности

NarrationMinimaxGroupLike(Protocol): paragraph_ids, text, after_scene_break

MinimaxText(frozen)
    text: str
    pause_counts: Mapping[str, int]          # ключи MINIMAX_PAUSE_KINDS, всегда все
    pauses_by_group: tuple[str | None, ...]  # вид паузы в конце каждой группы

build_minimax_text(groups, plan: NarrationDocumentPlan) -> MinimaxText
```

Таблица примеров (SC-006; уровни заголовков подряд, `chapter_level = 1`, `B` — тело):

| Группы | Метки в конце групп |
|---|---|
| `H1, B, B` | `H1<#1.5#>`, `B`, `B` (последняя — без метки) |
| `H2, H1, B` (серия `2 → 1`) | `H2`, `H1<#1.5#>`, `B` |
| `H1, H2, B` | `H1<#1.5#>`, `H2<#0.8#>`, `B` |
| `H3, H3, B` (серия, `Normal`) | `H3`, `H3<#0.8#>`, `B` |
| `B1, B2(after_scene_break)` | `B1<#2.0#>`, `B2` |
| `H1, B1(after_scene_break)` | `H1<#2.0#>` (совпадение: большая), `B1` |
| последняя группа книги — заголовок | метки нет |
| первая группа с `after_scene_break` | не бывает (R8: начало книги отметки не даёт) |

Инварианты: `text.replace(<каждая вставленная метка в конце группы>, "")` == `.tts.txt`; в тексте нет двух меток
подряд; меток ровно `sum(pause_counts.values())`.

## 8. Экспорт озвучки, состояние, bundle (FR-008; research R10)

`pipeline/narration_exports.py`:

```text
NarrationExports(frozen)                     # :61-130
    plan, docx_bytes, docx_error, pdf        # без изменений
    minimax: MinimaxText | None              # новое
    minimax_error: str | None                # класс исключения, если MiniMax не собран
```

Значение ключа `latest_narration_exports` и поля bundle `narration_exports` (одна форма, +1 ключ к 072):

| Ключ | Тип | Смысл |
|---|---|---|
| `docx_bytes`, `pdf_bytes`, `docx_unavailable_reason`, `pdf_unavailable_reason` | как в 072 | без изменений |
| `minimax_text` | `str \| None` | `.tts.minimax.txt` |

`_normalize_narration_exports` (`processing/processing_runtime.py:1657-1675`): пять ключей; `minimax_text` — `str`, иначе
`None`. Старый bundle без ключа → кнопки MiniMax нет.

## 9. Группа результата (FR-008)

| Файл | Ключ `artifact_paths` | Когда |
|---|---|---|
| `<stem>.result.tts.minimax.txt` | `tts_minimax_path` | MiniMax собран (непустой текст) |
| остальные члены 072 | как в 072 | как в 072 |

Суффиксы хранения: `_UI_RESULT_GROUP_SUFFIXES` + `.result.tts.minimax.txt`.
