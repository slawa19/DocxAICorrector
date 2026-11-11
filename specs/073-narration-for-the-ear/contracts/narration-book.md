# Контракт: файл книги для озвучки `<stem>.narration.json`, `schema_version: 1` (спека 073, FR-007, решение D-4)

Потребитель — отдельный инструмент поэтапной озвучки владельца (`D:\Temp\docxai-research\audiobook-studio\ARCHITECTURE.md`
§6.4 — его контракт импорта; с 2026-11-11 инструмент живёт в своём репозитории `slawa19/AudiobookStudio`, его сторона
контракта — `docs/NARRATION_BOOK.md` там). Этот документ — источник правды для стороны DocxAICorrector; пример §6.4 шире (название,
автор, язык) — этих полей здесь нет, потому что DocxAICorrector их не знает. Код имён избегает слова «manifest»: в группе
результата уже есть `.result.manifest.json` (другой файл) — здесь «файл книги», `narration_book`.

## 1. Формат файла

UTF-8, LF, `json.dumps(obj, ensure_ascii=False, indent=1)` + `"\n"`: знак ударения U+0301 и кириллица — как есть, без
`\u`-экранирования (Anti-regression 5). Порядок ключей — как в таблицах ниже.

## 2. Верхний уровень (набор ЗАКРЫТ)

| Ключ | Тип | Значение |
|---|---|---|
| `schema_version` | `int` | `1`; растёт только при несовместимом изменении (удаление/переименование поля, смена смысла) |
| `producer` | объект | §3 |
| `book` | объект | §4 |
| `chapter_heading_level` | `int \| null` | `NarrationDocumentPlan.chapter_level` (072, спека 074 FR-101/FR-103): **порог** — главы открывают заголовки этого уровня и выше (а не только этого уровня); это самый верхний уровень, при котором ни одна глава не длиннее лимита Studio (400 абзацев), а когда ни один не подходит — самый глубокий из присутствующих; `null` — заголовков с уровнем нет. Формат файла и схема не менялись |
| `chapters` | список | §5, по порядку |
| `segments` | список | §6, по порядку |
| `reading_glossary` | список | §7 |
| `stats` | объект | §8 |

Других ключей верхнего уровня нет. Инструмент на неизвестном ключе верхнего уровня останавливает импорт с номером версии
(`ARCHITECTURE.md` §6.4); добавление нового ключа верхнего уровня — значит новая `schema_version`. Внутри объектов новые
ключи в рамках версии 1 не добавляются без записи в Changelog спеки.

## 3. `producer`

| Ключ | Тип | Значение |
|---|---|---|
| `name` | `str` | `"DocxAICorrector"` |
| `version` | `str \| null` | git SHA кода, собравшего файл (`runtime/build_info.py:resolve_git_head()`, перенос `_safe_git_head` раннера — research R18); `null`, если кода вне git-checkout'а — не выдумывается |
| `run_id` | `str` | `context.run_id` прогона |
| `produced_at` | `str` | UTC, ISO 8601 с `Z`, секунды |

## 4. `book`

| Ключ | Тип | Значение |
|---|---|---|
| `source_name` | `str` | имя загруженного файла (`context.uploaded_filename`) |
| `source_token` | `str` | `context.source_token` (`<имя>:<размер>:<хэш>`) — ключ книги для инструмента (`ARCHITECTURE.md` §6.3) |

`title`, `author`, `language` — нет (Non-goals спеки: не выдумываются).

## 5. `chapters[]`

| Ключ | Тип | Значение |
|---|---|---|
| `ordinal` | `int` | с 1, по порядку |
| `title` | `str \| null` | текст абзаца плана `Heading 1`, открывшего главу (слитая серия 072 — «A. B»); `null` у главы до первого `Heading 1` |
| `segment_ordinals` | `list[int]` | ординалы её сегментов по порядку, непустой |

Правило (072, `pipeline/narration_document.py:130-160`, `StudioLimits.chapter_count_for_limits`): каждый абзац плана со
стилем `Heading 1` открывает главу; абзацы до первого `Heading 1` — отдельная глава с `title: null` (если они есть); книга
без `Heading 1` — одна глава с `title: null`. `len(chapters) == plan.studio_limits.chapter_count_for_limits`. Каждый
сегмент — ровно в одной главе; объединение `segment_ordinals` по порядку = `1..len(segments)`.

## 6. `segments[]`

| Ключ | Тип | Значение |
|---|---|---|
| `ordinal` | `int` | с 1, по порядку групп |
| `chapter_ordinal` | `int` | глава сегмента (§5) |
| `role` | `str` | `NarrationGroup.role` (роль первой записи группы; закрытый словарь ролей записей озвучки) |
| `heading_level` | `int \| null` | `NarrationGroup.heading_level` (только у роли `heading`) |
| `text` | `str` | `NarrationGroup.text` побайтно |
| `after_scene_break` | `bool` | `NarrationGroup.after_scene_break` (FR-006) |
| `pause_after` | `{"kind": str, "seconds": float} \| null` | §6.1 |
| `source_paragraph_ids` | `list[str]` | `NarrationGroup.paragraph_ids` (`pNNNN`; `""` у неадресуемой записи) — только происхождение, не идентичность |

**Инвариант контракта (тест на обеих сторонах):** `"\n\n".join(s["text"] for s in segments)` побайтно равен `.tts.txt`
того же прогона. Сегментов столько же, сколько групп; порядок тот же.

### 6.1 `pause_after`

| `kind` | Где | `seconds` по умолчанию | Замер (`D:\Temp\docxai-research\minimax-tts\RESEARCH.md`) |
|---|---|---|---|
| `chapter` | последний сегмент серии заголовков, ставшей абзацем плана `Heading 1` | 1.5 | тишина 1,88 с |
| `heading` | последний сегмент серии заголовков, ставшей абзацем плана `Normal` | 0.8 | 1,24 с |
| `scene_break` | сегмент перед сегментом с `after_scene_break` | 2.0 | 2,48 с |

Серии и ранги — из плана 072 (сегменты и абзацы плана идут шаг в шаг: абзац плана с `source_heading_level` поглощает
`len(paragraph_ids)` групп, иной — одну). Совпадение оснований — бо́льшие секунды (вид — тот, чьи секунды больше). У
последнего сегмента книги `pause_after = null`. Между абзацами тела — `null`: паузу абзаца задаёт инструмент
(`ARCHITECTURE.md` §8.2). `seconds` — значения по умолчанию из константы модуля; инструмент вправе заменить их своими
настройками книги без перегенерации.

## 7. `reading_glossary[]`

`[{"abbreviation": str, "reading": str}]` — принятые записи `ReadingGlossary.entries` (FR-004) в их порядке; пусто, если
словаря нет (`no_candidates`). Кандидаты без чтения, отказы и отправленный контекст — только в артефакте словаря, не здесь.

## 8. `stats`

| Ключ | Тип | Значение |
|---|---|---|
| `char_count` | `int` | `len(.tts.txt)` |
| `segment_count` | `int` | `len(segments)` |
| `chapter_count` | `int` | `len(chapters)` |
| `heading1_count` | `int` | `plan.studio_limits.heading1_count` |
| `scene_break_count` | `int` | сегментов с `after_scene_break` |
| `pause_counts` | `{chapter, heading, scene_break}` | сегментов каждого вида паузы |
| `excluded_count` | `int` | `audiobook_narration_summary.excluded_count` (исключённые абзацы прогона) |
| `excluded_by_reason` | `dict[str, int]` | там же |
| `reading_glossary_entry_count` | `int` | `len(reading_glossary)` |

## 9. Пример (синтетика)

```json
{
 "schema_version": 1,
 "producer": {"name": "DocxAICorrector", "version": "852d9d2", "run_id": "abc123", "produced_at": "2026-11-10T15:01:39Z"},
 "book": {"source_name": "kvazibu.docx", "source_token": "kvazibu.docx:1024:0f0f0f0f0f0f0f0f"},
 "chapter_heading_level": 1,
 "chapters": [
  {"ordinal": 1, "title": null, "segment_ordinals": [1]},
  {"ordinal": 2, "title": "Часть первая. Квазибург", "segment_ordinals": [2, 3, 4, 5]}
 ],
 "segments": [
  {"ordinal": 1, "chapter_ordinal": 1, "role": "body", "heading_level": null, "text": "Посвящается городу.",
   "after_scene_break": false, "pause_after": null, "source_paragraph_ids": ["p0001"]},
  {"ordinal": 2, "chapter_ordinal": 2, "role": "heading", "heading_level": 2, "text": "Часть первая",
   "after_scene_break": false, "pause_after": null, "source_paragraph_ids": ["p0002"]},
  {"ordinal": 3, "chapter_ordinal": 2, "role": "heading", "heading_level": 1, "text": "Квазибург",
   "after_scene_break": false, "pause_after": {"kind": "chapter", "seconds": 1.5}, "source_paragraph_ids": ["p0003"]},
  {"ordinal": 4, "chapter_ordinal": 2, "role": "body", "heading_level": null, "text": "Ста́рый за́мок стоял на холме.",
   "after_scene_break": false, "pause_after": {"kind": "scene_break", "seconds": 2.0}, "source_paragraph_ids": ["p0004"]},
  {"ordinal": 5, "chapter_ordinal": 2, "role": "body", "heading_level": null, "text": "Утром пришли гости.",
   "after_scene_break": true, "pause_after": null, "source_paragraph_ids": ["p0006"]}
 ],
 "reading_glossary": [{"abbreviation": "ABC", "reading": "а-бэ-цэ"}],
 "stats": {"char_count": 101, "segment_count": 5, "chapter_count": 2, "heading1_count": 1, "scene_break_count": 1,
           "pause_counts": {"chapter": 1, "heading": 0, "scene_break": 1}, "excluded_count": 1,
           "excluded_by_reason": {"fragment": 1}, "reading_glossary_entry_count": 1}
}
```

(`char_count` в примере условный; серия `2 → 1` слита в план 072 как «Часть первая. Квазибург» — название главы.)
