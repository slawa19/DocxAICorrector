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
    reading_glossary_rerequested_count: int   # кандидатов во втором (повторном) запросе
    reading_glossary_unresolved_count: int    # без принятого чтения и после повторного запроса (SC-010: 0)
    reading_glossary_batch_count: int         # пакетов первого прохода + повторного запроса
    reading_glossary_call_count: int          # вызовов модели шага, включая повторы
    reading_glossary_retry_count: int         # повторов пакетов по политике блока
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

READING_GLOSSARY_BATCH_SIZE = 40

READING_GLOSSARY_STATUSES = ("built", "no_candidates", "stopped")     # решение владельца 2026-11-10: нет partial/empty/failed
    built         — все пакеты (первый проход и один повторный запрос) получили разборчивый ответ;
                    unresolved_count == 0 — обычный исход; > 0 — WARNING audiobook_reading_glossary_unresolved (review data)
    no_candidates — кандидатов нет, вызова нет
    stopped       — Stop перед шагом, перед пакетом или во время вызова
    (модель недоступна — НЕ статус: исключение ReadingGlossaryUnavailable, прогон падает — research R7)
READING_REJECTION_REASONS = ("not_a_candidate", "empty_reading", "latin_in_reading", "digit_in_reading", "not_cyrillic_reading", "duplicate")
READING_UNAVAILABLE_REASONS = ("error", "empty_response", "no_json", "invalid_json", "invalid_shape", "prompt_unavailable")
    # последняя причина пакета, исчерпавшего попытки; неповторяемая ошибка транспорта — "error" сразу

class ReadingGlossaryUnavailable(RuntimeError): reason: str, batch_index: int, attempts: int, error_class: str | None

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
    rejected_by_reason: Mapping[str, int]   # по всем ответам обоих проходов
    rerequested: tuple[str, ...]            # написания, ушедшие в повторный запрос
    unresolved: tuple[str, ...]             # без чтения и после него (только в артефакт, не в лог)
    batch_count: int; call_count: int; retry_count: int
    prompt_tokens: int | None; completion_tokens: int | None; cost_usd: float | None
    artifact_path: str | None
    def entry_for(abbreviation) -> ReadingEntry | None

reading_candidate_units(text: str) -> tuple[str, ...]
    пусто, если абзац целиком заглавными (форма all_caps); иначе letter_series(…, digits_inside=True) с маской
    адресов, где заглавных ≥ 2 и заглавных > строчных, кроме формы roman_numerals

extract_reading_candidates(paragraphs) -> tuple[ReadingCandidate, ...]
    по всем абзацам; частота desc, затем первое появление; первые MAX — sent=True

run_reading_glossary(*, paragraphs, client, model_id, max_retries, should_stop, log_event, filename, artifact_context,
                     request_text_completion_fn=request_text_completion, sleep_fn=time.sleep,
                     write_artifact_fn=_write_run_glossary_artifact) -> ReadingGlossary
    пакеты по 40 → на пакет до max_retries попыток request_text_completion_fn(client, request,
    usage_stage=STAGE_AUDIOBOOK_READING_GLOSSARY, should_stop=should_stop); повтор — на is_retryable_error,
    _is_non_completed_response_error (с _boost_request_output_budget при обрезке) и неразборчивом ответе;
    пауза sleep_fn(retry_backoff_seconds(attempt)); затем один повторный запрос кандидатов без чтения (те же правила);
    пакет без разборчивого ответа после всех попыток → raise ReadingGlossaryUnavailable

retry_backoff_seconds(attempt: int) -> float      # generation/_generation.py; min(2 ** (attempt - 1), 8), один источник для блока и словаря

parse_reading_glossary_response(raw_text, *, sent: Sequence[ReadingCandidate]) -> tuple[entries, rejected_by_reason]
    _load_json_object; список "readings"; запись принимается, если abbreviation побайтно равно отправленному,
    reading непуст после strip, без буквы LATIN и без цифры Nd, и abbreviation ещё не принят

reading_section_for_block(glossary: ReadingGlossary | None, source_texts: Sequence[str]) -> str
    кандидатные единицы исходника по порядку первого появления ∩ glossary.entries →
    render_glossary_prompt_section([GlossaryTerm(source_term=a, target_term=r)], header=HEADER, max_chars=2000); иначе ""

run_reading_glossary_phase(*, context, dependencies, emitters, state, initialization, emit_failed_result_fn)
        -> PipelineResult | None
    только операция audiobook: абзацы из context.jobs (ID, narration_exclusion_reasons is None, _block_source_texts)
    → run_reading_glossary(max_retries=context.max_retries) → state.audiobook_reading_glossary; None — продолжать.
    ReadingGlossaryUnavailable → present_error("audiobook_reading_glossary_failed", …), emit_state(last_error=…,
    latest_docx_bytes=None), emit_failed_result_fn(...) — тот же набор, что handle_block_generation_failure
    (pipeline/block_failures.py:135-243), без persist_terminal_job_result; возвращает этот исход (прогон «ошибка»)
```

Артефакт (`.run/run_glossaries/<run>_<ms>.json`, пишется, если вызов сделан — и при `built`, и перед падением шага):

```text
{schema: "audiobook_reading_glossary/v1", filename, run_id, model, status,
 candidates: [{abbreviation, occurrences, sent, rerequested, resolved}], readings: [{abbreviation, reading}],
 unresolved: [...], rejected_by_reason: {...}, batches: [{index, pass: "first"|"rerequest", size, attempts}],
 usage: {prompt_tokens, completion_tokens, cost_usd}}
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

ResultArtifactWriter.__call__(..., narration_book_json: str | None = None)          # :151-166, последним
```

Объявления состояния построены WP-D (`pipeline/contracts.py:297-302`). Аргумента писателя для MiniMax WP-D не добавил
(решение D-4 пришло позже); аргумент `narration_book_json` в протокол добавляет WP-J вместе с писателем.

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

## 7. Файл книги для озвучки (FR-007, решение D-4; research R9, R18; контракт — `contracts/narration-book.md`)

`pipeline/narration_book.py` (новый, чистый: без I/O, без Streamlit, без python-docx):

```text
NARRATION_BOOK_SCHEMA_VERSION = 1
NARRATION_BOOK_TOP_LEVEL_KEYS = ("schema_version", "producer", "book", "chapter_heading_level", "chapters",
                                 "segments", "reading_glossary", "stats")             # закрытый набор
NARRATION_PAUSE_KINDS = ("chapter", "heading", "scene_break")
NARRATION_PAUSE_DEFAULT_SECONDS = {"chapter": 1.5, "heading": 0.8, "scene_break": 2.0}   # замер MiniMax (RESEARCH.md)

NarrationBookGroupLike(Protocol): paragraph_ids, role, heading_level, text, after_scene_break

NarrationBookProducer(frozen): version: str | None, run_id: str, produced_at: str       # name — константа
NarrationBookSource(frozen):   source_name: str, source_token: str
NarrationBookGlossaryEntryLike(Protocol): abbreviation, reading

NarrationBook(frozen)
    payload: Mapping[str, object]            # объект JSON в порядке ключей контракта
    pause_kinds: tuple[str | None, ...]      # вид паузы сегмента, по порядку групп (для теста и учёта)
    pause_counts: Mapping[str, int]          # ключи NARRATION_PAUSE_KINDS, всегда все
    chapter_count: int
    def to_json(self) -> str                 # json.dumps(payload, ensure_ascii=False, indent=1) + "\n"

build_narration_book(*, groups, plan: NarrationDocumentPlan, glossary_entries, producer, source,
                     excluded_count: int, excluded_by_reason: Mapping[str, int],
                     pause_seconds: Mapping[str, float] = NARRATION_PAUSE_DEFAULT_SECONDS) -> NarrationBook
```

Алгоритм: план 072 и группы идут шаг в шаг — абзац плана с `source_heading_level is not None` (серия заголовков)
поглощает `len(paragraph_ids)` групп (группа-заголовок всегда из одной записи), любой другой — одну группу; абзац плана
`Heading 1` открывает главу (до первого — глава с `title: null`, если есть сегменты); последнему сегменту серии —
`chapter` (`Heading 1`) или `heading` (`Normal`); сегмент перед сегментом с `after_scene_break` — `scene_break`;
совпадение — бо́льшие секунды; последнему сегменту книги — `null`. Расхождение шагов (сумма поглощённых групп ≠ числу
групп) → `ValueError` наружу (его ловит поздний этап — WARNING, книга без файла).

Таблица примеров (SC-006; каждая строка — целая книга, `B` — тело, `Hn` — заголовок уровня n; в книгах с `H1`
`chapter_level = 1`; последняя группа книги в каждой строке — тело, кроме оговорённой):

| Группы книги | `pause_after.kind` по сегментам | Главы |
|---|---|---|
| `H1, B, B` | `chapter`, `null`, `null` (последний — без паузы) | 1: «H1» [1–3] |
| `B0, H1, B` | `null`, `chapter`, `null` | 1: `null` [1]; 2: «H1» [2–3] |
| `H2, H1, B` (серия `2 → 1`) | `null`, `chapter`, `null` | 1: «H2. H1» [1–3] |
| `H1, H2, B` | `chapter`, `heading`, `null` | 1: «H1» [1–3] |
| `H1, B, H3, H3, B` (серия `3 → 3`, `Normal`) | `chapter`, `null`, `null`, `heading`, `null` | 1: «H1» [1–5] |
| `B1, B2(after_scene_break)` | `scene_break`, `null` | 1: `null` [1–2] (книга без заголовков) |
| `H1, B1(after_scene_break), B2` | `scene_break` (2,0 > 1,5), `null`, `null` | 1: «H1» [1–3] |
| `H1, B, H1` (заголовок — последний сегмент) | `chapter`, `null`, `null` | 1: «H1» [1–2]; 2: «H1» [3] |
| только `H3, B, H3, B` (уровней 1–2 нет) | `chapter`, `null`, `chapter`, `null` | `chapter_level = 3`: 1 [1–2]; 2 [3–4] |
| ни одного заголовка | все `null`, кроме разделителей | одна глава `null` |

Инварианты: `"\n\n".join(s["text"] for s in payload["segments"]) == "\n\n".join(g.text for g in groups)` побайтно;
`len(chapters) == plan.studio_limits.chapter_count_for_limits`; каждый сегмент ровно в одной главе; ключи верхнего
уровня == `NARRATION_BOOK_TOP_LEVEL_KEYS`; у сегмента не больше одного вида паузы.

`runtime/build_info.py` (новый): `resolve_git_head(project_root: Path | None = None) -> str | None` — перенос
`_safe_git_head` / `_resolve_git_pointer_path` / `_read_git_head_from_files` раннера
(`tests/artifacts/real_document_pipeline/run_lietaer_validation.py:479-566`) в продукт; раннер затем импортирует её
(одна копия). `None` вне git-checkout'а.

## 8. Экспорт озвучки, состояние, bundle (FR-008; research R10)

`pipeline/narration_exports.py`:

```text
NarrationExports(frozen)                     # :61-130
    plan, docx_bytes, docx_error, pdf        # без изменений
    book: NarrationBook | None               # новое
    book_error: str | None                   # класс исключения, если файл книги не собран

build_narration_exports(*, groups, source_name, log_event, export_pdf=None,
                        book_inputs: NarrationBookInputs | None = None)
NarrationBookInputs(frozen): glossary_entries, producer, source, excluded_count, excluded_by_reason
    # None — файл книги не строится (вызовы 072 без этого аргумента — побайтно прежние)
```

Значение ключа `latest_narration_exports` и поля bundle `narration_exports` (одна форма, +1 ключ к 072):

| Ключ | Тип | Смысл |
|---|---|---|
| `docx_bytes`, `pdf_bytes`, `docx_unavailable_reason`, `pdf_unavailable_reason` | как в 072 | без изменений |
| `book_json` | `str \| None` | текст `.narration.json` |

`_normalize_narration_exports` (`processing/processing_runtime.py:1657-1675`): пять ключей; `book_json` — непустой `str`,
иначе `None`. Старый bundle без ключа → кнопки файла книги нет.

## 9. Группа результата (FR-008)

| Файл | Ключ `artifact_paths` | Когда |
|---|---|---|
| `<stem>.result.narration.json` | `narration_book_path` | файл книги собран (непустой текст) |
| остальные члены 072 | как в 072 | как в 072 |

Суффиксы хранения: `_UI_RESULT_GROUP_SUFFIXES` + `.result.narration.json` (пересечения нет: не кончается на
`.result.manifest.json`, `.result.meta.json`).
