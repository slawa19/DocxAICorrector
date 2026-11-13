# Data Model: аудиокнига — технический проход

**Spec**: [spec.md](spec.md) | **Plan**: [plan.md](plan.md) | **Research**: [research.md](research.md)

Сущности новые или меняющиеся. Пути — относительно `src/docxaicorrector/`. Все словари значений ЗАКРЫТЫ: неизвестное
значение — `ValueError` на границе (как `job_parsing.coerce_paragraph_regions`, `pipeline/job_parsing.py:25-40`).

## 1. Причина исключения абзаца (FR-003)

Константы — `core/models.py`, рядом с `PARAGRAPH_REGION_VALUES` (`:51-62`):

| Константа | Значение | Сигнал (только роль, регион, форма) |
|---|---|---|
| `NARRATION_EXCLUSION_IMAGE` | `image` | роль подготовки `image` |
| `NARRATION_EXCLUSION_TABLE` | `table` | роль `table` (`RawTable`, `document/extraction.py:676-680`) |
| `NARRATION_EXCLUSION_CAPTION` | `caption` | роль `caption` (`document/roles.py:23`, `:283-296`) |
| `NARRATION_EXCLUSION_TOC` | `toc` | `_is_toc_structural_role` (`toc_header`/`toc_entry`) |
| `NARRATION_EXCLUSION_INDEX` | `index` | регион `back_matter` и раздел `index` (`core/models.py:78`) |
| `NARRATION_EXCLUSION_APPARATUS` | `apparatus` | регион `back_matter`, раздел не `index` |
| `NARRATION_EXCLUSION_NOTES_IN_BODY` | `notes_in_body` | отметка спеки 067 FR-001 (О-2 плана; на подтверждении); со спеки 077 — без абзаца-начала главы, который отметка читает как серию из одной записи (`specs/077-epigraph-opening-narrated/spec.md`), только для озвучки; со спеки 079 серия из двух и более записей отмечается, только если хотя бы одна её часть — ссылка (`specs/079-notes-run-must-cite/spec.md`; это сама отметка, для всех операций) |
| `NARRATION_EXCLUSION_FRAGMENT` | `fragment` | форма: нет буквенного токена ≥ 3 букв ИЛИ буквы < ½ непробельных; не для ролей `heading`, `epigraph`, `attribution`, `dedication` (О-1) |

`NARRATION_EXCLUSION_REASONS = frozenset({...})`. Приоритет — порядок строк таблицы; у абзаца одна причина или `None`.

**Поле задания** (`document/semantic_blocks.build_editing_jobs`, только для `audiobook`):
`narration_exclusion_reasons: list[str | None]` — длина = `len(paragraph_ids)`. Для `translate`/`edit` ключа нет (задание
побайтно прежнее). **Payload**: `BlockExecutionPayload.narration_exclusion_reasons: list[str | None] | None = None`
(`pipeline/contracts.py:379-418`); `None` = «производитель не вычислял» = ни один не исключён (как
`notes_in_body_paragraph_ids`). Разбор: `job_parsing.coerce_narration_exclusion_reasons` — длина должна совпадать с
`paragraph_ids`, значения — из закрытого словаря или `None`.

## 2. План блока аудиокниги (FR-003, R2)

`pipeline/audiobook_plan.py`:

```text
AudiobookExcludedParagraph(frozen): paragraph_id: str, reason: str, source_text: str
AudiobookBlockPlan(frozen):
    paragraph_ids: tuple[str, ...]          # все ID блока, в порядке
    send_ids: tuple[str, ...]               # озвучиваемые ID (знаменатель блока), в порядке
    send_text_with_markers: str             # "[[DOCX_PARA_id]]\n<текст>" через "\n\n", только send_ids
    send_text: str                          # те же абзацы без маркеров
    send_source_texts: tuple[str, ...]      # исходный текст каждого send_id
    excluded: tuple[AudiobookExcludedParagraph, ...]
build_audiobook_block_plan(payload) -> AudiobookBlockPlan | None   # None: нет paragraph_ids / нет причин
merge_audiobook_dispositions(plan, generated: str) -> MarkerPreservedBlockText
```

`merge_…`: ID ответа должны совпасть с `send_ids` (иначе `ValueError` — это дефект кода, не модели); исключённые
вставляются на свои места как `ParagraphDisposition(paragraph_id, text=source_text, status=policy_kept_source)`.

## 3. Чистка, эмодзи, остаток, покрытие (FR-005, FR-006, FR-007)

### 3.1 `text/narration_cleanup.py`

```text
CleanupStats(frozen): internal_token_count, html_tag_count, html_entity_count, emoji_sequence_count,
                      decoration_marker_count, markdown_syntax_count: int
CleanupResult(frozen): text: str, stats: CleanupStats
clean_narration_paragraph(text: str) -> CleanupResult        # чистая, идемпотентная
```

Порядок шагов и что именно снимается — research R8. Идемпотентность — тестом (`clean(clean(x)) == clean(x)`).

### 3.2 `text/unicode_emoji_data.py` (сгенерирован) и сканер

`UNICODE_EMOJI_DATA_VERSION = "15.1.0"`, `UNICODE_EMOJI_DATA_SHA256`, кортежи диапазонов `(start, end)` для
`EMOJI`, `EMOJI_PRESENTATION`, `EMOJI_MODIFIER`, `EMOJI_MODIFIER_BASE`, `EMOJI_COMPONENT`, `EXTENDED_PICTOGRAPHIC`.
Сканер `text/narration_cleanup.py::find_emoji_sequences(text) -> list[tuple[int, int]]` — грамматика research R1.

### 3.3 `text/narration_residue.py` — классы остатка (таблица FR-006)

| Класс (`residue_class`) | Форма (по категориям Unicode, без словарей) | Исправляется |
|---|---|---|
| `digits` | любой символ `Nd` или надстрочная/подстрочная цифра (`No` из блоков `U+2070–U+209F`, `U+00B2`, `U+00B3`, `U+00B9`) | да |
| `roman_numerals` | токен только из `IVXLCDM` длиной ≥ 2 (границы — не буква) или символ категории `Nl` | да |
| `symbols` | символ `Sc` или `Sm`, либо `%`, `№`, `§`, `&` внутри текста | да |
| `all_caps` | все буквы абзаца прописные и есть ≥ 2 слов из ≥ 4 букв | да |
| `url_or_domain` | схема `[a-z][a-z0-9+.-]*://` или `www.`; либо `слово.слово` без пробела, где после последней точки ≥ 2 букв, кроме многоточия и чисел | да |
| `tag_form` | `[слово]` / `[слово слово]` латиницей строчными (`\[[a-z]+(?: [a-z]+)?\]`) | да |
| `html_left` | синтаксис тега R8 после чистки | нет (контроль неполной чистки) |
| `emoji_left` | последовательность R1 после чистки | нет |

```text
ResidueFinding(frozen): residue_class: str, count: int, sample: str        # sample ≤ 120 знаков вокруг 1-го вхождения
detect_narration_residue(text: str) -> tuple[ResidueFinding, ...]        # пусто = чисто
REPAIRABLE_RESIDUE_CLASSES = frozenset({digits, roman_numerals, symbols, all_caps, url_or_domain, tag_form})
```

Счётчик класса — число ВХОЖДЕНИЙ (REVIEW №18), образцов в событиях — не больше 3 на класс.

### 3.4 `text/narration_coverage.py`

```text
CoverageResult(frozen): long_word_count: int, found_count: int, ratio: float | None
paragraph_coverage(source: str, answer: str) -> CoverageResult
COVERAGE_REVIEW_THRESHOLD = 0.6         # предварительный (research R9)
COVERAGE_MIN_LONG_WORDS = 4; COVERAGE_MIN_TOKENS = 6; LONG_WORD_MIN_LETTERS = 6; STEM_LETTERS = 5
```

## 4. Запись исправления (FR-006, R5)

`pipeline/audiobook_repair.py`:

```text
RepairItem(frozen): paragraph_id: str, text: str, residue_classes: tuple[str, ...]
RepairOutcome(frozen):
    status: "accepted" | "rejected" | "failed" | "skipped"
    reason: None | "marker_mismatch" | "empty_paragraph" | "error" | "stopped"
    texts: Mapping[str, str]            # итог по paragraph_id; при не-accepted = исходные item.text
    error_class: str | None
    call_made: bool                     # был ли вызов API
repair_block_residue(*, client, model_id, system_prompt, items: Sequence[RepairItem],
                     context_before: str, context_after: str,
                     should_stop: Callable[[], bool], log_event, block_index: int, filename: str) -> RepairOutcome
STAGE_AUDIOBOOK_REPAIR = "audiobook_repair"      # core/model_accounting.py
```

## 5. Запись абзаца озвучки и `needs_review` (FR-006, FR-007, R7, R8)

`pipeline/audiobook_pass.py` (WP-G):

```text
NarrationParagraphRecord(frozen):
    paragraph_id: str, block_index: int, role: str           # роль подготовки (payload.structural_roles)
    text: str                                                # итоговый текст для .tts.txt
    needs_review_reasons: tuple[str, ...]                    # см. ниже
    residue_before: tuple[ResidueFinding, ...]               # до исправления
    residue_after: tuple[ResidueFinding, ...]                # итог
    coverage: CoverageResult
NEEDS_REVIEW_REASONS = {
    "empty_answer", "source_restored", "source_fallback",    # R7
    "residue",                                               # остаток классов после исправления
    "repair_failed",                                         # исправление не принято / не сделано (Stop)
    "low_coverage",                                          # ratio < порога
}
```

**Состояние прогона** (`pipeline/contracts.ProcessingState`, `:259`) — новые поля:

| Поле | Тип | Смысл |
|---|---|---|
| `narration_paragraphs` | `list[NarrationParagraphRecord]` | сборка `.tts.txt` (заменяет `narration_chunks`, `:266`) |
| `narration_expected_paragraph_ids` | `list[str]` | знаменатель: озвучиваемые ID, записанные ДО ответа модели |
| `narration_exclusions` | `list[dict]` `{paragraph_id, block_index, reason}` | все исключения FR-003 с адресами |
| `narration_repair_counters` | `dict[str, int]` | `block_count`, `call_count`, `accepted_block_count`, `failed_call_count`, `skipped_stopped_count`, `rejected_by_reason.*` |

Удаляются (R7, FR-002): `narration_chunks`, `excluded_narration_block_count` (заменён исключениями по причинам),
`narration_excluded_source_fallback_block_count/_chars/_paragraphs`, `narration_excluded_omitted_paragraph_count/_chars/
_paragraphs`, `narration_postprocess_paragraph_shortfall_group_count/_paragraph_count` (`:306-312`).
`narration_joined_sentence_continuation_count` остаётся и получает пару `narration_joined_paragraph_id_pairs: list[tuple[str, str]]`.

## 6. Итог озвучки на прогон (публикуется в `ui_audiobook_artifact_saved` и отчёте раннера)

| Поле | Определение |
|---|---|
| `expected_paragraph_count` | `len(narration_expected_paragraph_ids)` — знаменатель SC-003 |
| `delivered_paragraph_count` | число записей `narration_paragraphs` |
| `missing_paragraph_ids` | ожидаемые ID без записи (должно быть `[]`) |
| `paragraph_boundary_check` | `"ok"` / `"mismatch"`: разбор итогового `.tts.txt` по `"\n\n"` даёт `delivered − joins` абзацев и каждый текст записи стоит на своём месте |
| `deterministic_join_count`, `deterministic_join_pairs` | склейки разорванных предложений, пары ID |
| `excluded_by_reason` | `{reason: count}` + `excluded_paragraph_ids_by_reason` |
| `residue_before_by_class`, `residue_after_by_class` | `{class: {paragraphs, occurrences}}` |
| `needs_review_paragraph_count`, `needs_review_by_reason` | по `needs_review_reasons` |
| `repair_*` | счётчики §5 |
| `coverage_not_measured_count`, `coverage_low_count` | сигнал R9 |
| `char_count`, `tts_text_path` | как сейчас |

Убираются (FR-002, D-3, R7): `tag_count`, `mode`, `excluded_blocks`, `excluded_source_fallback_*`, `excluded_omitted_*`,
`postprocess_paragraph_shortfall_*`.

## 7. Конфиг и контракт вызова (FR-001, FR-002, FR-008)

- Удаляются: `AppConfig.audiobook_postprocess_default` (`core/config.py:272`), ключ TOML `audiobook_postprocess_default`,
  переменная `DOCX_AI_AUDIOBOOK_POSTPROCESS_DEFAULT`, `app_config["audiobook_postprocess_enabled"]`,
  `RunProfile.audiobook_postprocess_enabled` и поле в `corpus_registry.toml`, `ResolvedRuntimeConfig.audiobook_postprocess_enabled`,
  поле результата `audiobook_postprocess_enabled` (`processing_runtime.py:1695`, `late_phases.py:1725`). Старый ключ в
  пользовательском `config.toml` → `config_key_ignored` (`core/config.py:1122`).
- Остаётся и начинает управлять основным путём: `audiobook_model` (`core/config.py:273`) — `contracts/audiobook-config.md`.
- **Пара языков для `audiobook` — отсутствие**: `ProcessingContext.source_language/target_language: str | None`
  (`pipeline/contracts.py:246-247`); `None` для `audiobook`, строка для `translate`/`edit`. Нормализация — одна функция
  `core/audiobook_mode.language_pair_for_operation(operation, source, target) -> tuple[str | None, str | None]`, её
  вызывают UI (`ui/_app.py`), старт обработки (`processing/processing_runtime.py:2090-2092`), `pipeline/setup.py:174-175`,
  `pipeline/_pipeline.py:989-990`, профили (`validation/profiles.py:314-315`) и маркер подготовки
  (`processing_runtime.py:1678`: для `audiobook` суффикса языков нет).
