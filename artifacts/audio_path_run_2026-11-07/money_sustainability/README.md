# Прогон `20261107T_061_audio_money` — замер спеки 061 на одной книге

Money & Sustainability (en→ru), `processing_operation=audiobook`, профиль
`ui-parity-standalone-audiobook`, модель `openrouter:google/gemini-3.1-flash-lite-preview`,
маркеры включены, reader cleanup выключен, код `main` на `769dfac` (слияние спеки 061),
2026‑11‑07, 651,9 с, 310 вызовов, **$0.496948** по реестру прогона.

Это пункт 1 «Порядка исполнения» спеки 061: один платный прогон одной книги после P1. Книга,
профиль и модель те же, что у `20260809T_059_audio_money`
(`artifacts/audio_path_run_2026-08-09/money_sustainability/`), поэтому числа сравнимы — с
оговоркой, что модель от прогона к прогону отвечает по-разному (спека 056, `:214-216`).

`git_head=None` в `run_summary.txt:146` — не потеря: прогон шёл из бокового worktree, где git
под WSL не читает `.git`-файл с windows-путём (AGENTS.md, «Боковые worktree»). Коммит —
`769dfac`. Полный отчёт (27 МБ) и `.tts.txt` остаются в
`tests/artifacts/real_document_pipeline/runs/20261107T_061_audio_money/` и в git не едут.

## Файлы

- `run_summary.txt` — сводка прогона как её записал прогонщик (копия).
- `result_notices.json` — три уведомления, которые прогон опубликовал на экран
  (`runtime.state.latest_result_notices` из отчёта).
- `source_text_paragraphs.json` — все абзацы, у которых в доставленном DOCX стоит их
  собственный исходный текст (`omitted` и `source_restored`), в той же форме, что у
  2026‑08‑09: `{block_index, paragraph_id, paragraph_status, text}` из
  `runtime.state.processed_paragraph_registry`. Восемь записей, все `omitted`.
- `tts_excerpt_first40.txt` — первые 40 строк `.tts.txt`, только чтобы было видно форму.

## Критерии спеки 061

| критерий | что требуется | замерено | вердикт |
|---|---|---|---|
| SC-001 (а) | `source_restored`, произнесённых в `.tts.txt`, — 0 | `source_restored` в реестре — **0** из 1318; произнесённых — **0** | PASS на одной книге |
| SC-001 (б) | строк `.tts.txt` с нулевой долей кириллицы вне аппарата — 0 | **1** строка из 1292 с буквами: `L3 "(i)"` — номер страницы титула (`p0002`, блок 2), то есть аппарат; вне аппарата — **0** | PASS на одной книге |
| SC-001 (в) | удержанные из озвучки абзацы с текстом исходника | 8 `omitted` (5 987 симв.), ни один не найден в `.tts.txt` | соответствует FR-006 |
| SC-002 (а) | `marker_chunk_collapse` на первой попытке не доставляет исходник | `model_output_discarded_reason_counts={}` (`run_summary.txt:62`) | PASS |
| SC-002 (б) | `marker_chunk_merge_retry_count ≥ 1` там, где раньше был discard | `0` (`run_summary.txt:44`); слияний в прогоне не было вовсе (ни одного `merged_marker_chunk` среди 27 отклонённых попыток) | **НЕ ПРОВЕРЕНО**: путь FR-001 на этой книге не сработал |
| SC-003 | доля вызовов, добавленных FR-001, ≤ 0,98 % | **0 / 310 = 0 %** | PASS, но вакуумно (см. SC-002 б) |

SC-001 по тексту спеки определён на ЧЕТЫРЁХ книгах (пункт 6 порядка); здесь — одна, и это
доказательство только для неё.

### Чем посчитан SC-001 (б)

Скрипт запускался под WSL как `python3 -I sc001.py <tts.txt> <report.json>`. Теги озвучки
`[...]` (`[serious]`, `[short pause]`) вычищаются до подсчёта: они латинские по построению и
не произносятся как текст. До вычистки таких строк было три (`L3 "[serious] (i)"`,
`L1341`/`L2513 "[short pause]"`), после — одна.

```python
import json, re, sys, unicodedata

tts_path, report_path = sys.argv[1], sys.argv[2]
raw = open(tts_path, encoding="utf-8").read()
lines = raw.split("\n")
TAG = re.compile(r"\[[^\[\]\n]{1,40}\]")

def share(s):
    ls = [ch for ch in s if ch.isalpha()]
    if not ls:
        return None, 0
    cyr = sum(1 for ch in ls if "CYRILLIC" in unicodedata.name(ch, ""))
    return cyr / len(ls), len(ls)

counted, zero, low = 0, [], []
for no, line in enumerate(lines, 1):
    spoken = TAG.sub("", line)
    sh, n = share(spoken)
    if sh is None:
        continue
    counted += 1
    if sh == 0:
        zero.append((no, spoken.strip()))
    elif sh < 0.5:
        low.append((no, round(sh, 3), spoken.strip()))
print(f"tts lines={len(lines)} lines_with_letters_after_tag_strip={counted}")
print(f"zero_cyrillic_share_lines={len(zero)}")
for no, t in zero:
    print(f"  L{no}: {t[:200]!r}")
print(f"lines_with_0<share<0.5={len(low)}")

r = json.load(open(report_path, encoding="utf-8"))
reg = r["runtime"]["state"]["processed_paragraph_registry"]
for status in ("source_restored", "omitted"):
    entries = [e for e in reg if e.get("paragraph_status") == status]
    spoken = [e for e in entries if len(e["text"].strip()) >= 20 and e["text"].strip()[:60] in raw]
    print(f"registry {status}={len(entries)}; found verbatim in tts={len(spoken)}")
```

Вывод: `tts lines=2613 lines_with_letters_after_tag_strip=1292`, `zero_cyrillic_share_lines=1`
(`L3: '(i)'`), `lines_with_0<share<0.5=0`, `registry source_restored=0; found verbatim in
tts=0`, `registry omitted=8; found verbatim in tts=0`.

Отнесение `(i)` к аппарату — моё, по позиции (второй абзац книги, титул), а не по полю
региона: регион абзаца в отчёт не пишется. Тот же титул назван регионом в
`src/docxaicorrector/pipeline/block_execution.py:283-285`.

## Цена: что добавили переспросы

| величина | вызовов | доля от 310 |
|---|---:|---:|
| ретраи по слиянию (FR-001, `marker_chunk_merge_retry_count`) | 0 | 0 % |
| ретраи по маркерам (`marker_validation`) | 20 | 6,45 % |
| recovery после исчерпания ретраев | 5 | 1,61 % |
| лестница деградации (2 блока × 3 вызова) | 6 | 1,94 % |
| всё сверх первой попытки | 31 | 10,0 % |

Обе ступени лестницы сработали по `paragraph_split_detected` (блоки 127 и 203), не по
слиянию; оба блока спасены полностью (6 из 6 абзацев переведены, 0 неспасённых).
**Доля лестницы 1,94 % выше 0,98 %, измеренных 2026‑08‑08** (3 вызова к 307, один блок) — и
ниже 2,84 % прогона 2026‑08‑09 (9 к 317, два блока) до спеки 061. Лестница сработала на
двух блоках, как 2026‑08‑09; спека 061 её не меняла. Anti-regression спеки
(«Лестница: стоимость на прогоне ≤ измеренной (SC-003)») по букве на этом прогоне НЕ
выполнена; различие объясняется числом сработавших блоков (1 против 2), а не ценой одного
срабатывания (3 вызова на блок в обоих случаях).

Все 310 ответов пришли через Responses: `api_path_counts={"responses": 310}`
(`run_summary.txt:61`); запасной путь chat.completions на дефолтном провайдере не
понадобился ни разу.

## До и после

| величина | `20260809T_059_audio_money` (`1b52ded`) | `20261107T_061_audio_money` (`769dfac`) |
|---|---:|---:|
| вызовов модели | 317 | 310 |
| цена, $ | 0.536254 | 0.496948 |
| длительность, с | 828,1 | 651,9 |
| `paragraph_disposition_counts.accepted` | 1308 | 1310 |
| `omitted` абзацев / символов | 8 / 4455 | 8 / 5987 |
| `source_restored` абзацев / символов | 2 / 595 | 0 / 0 |
| `retry_required` | — | 0 |
| `model_output_discarded_reason_counts` | `{"marker_chunk_collapse": 1}` | `{}` |
| `marker_chunk_merge_retry_count` | счётчика не было | 0 |
| ретраев (маркеры + recovery) | 29 (23 + 6) | 25 (20 + 5) |
| лестница: блоков / вызовов | 2 / 9 | 2 / 6 |
| `narration_excluded_source_fallback_block_count` | 0 | 0 |
| `narration_artifact.excluded_omitted_paragraph_count` / `_chars` | 8 / 4455 | 8 / 5987 |
| `narration_excluded_blocks` | 59 | 59 |
| `narration_char_count` | 468 283 | 467 958 |
| `acceptance_passed` | False (3 проверки) | **True** |
| `translation_quality_status` | pass | warn |

`source_restored` 2 → 0 — не заслуга FR-001 на этом прогоне. Абзац `p0654`, который
2026‑08‑09 был восстановлен из исходника после слияния, сегодня сжался БЕЗ поглотившего
соседа (`marker_chunk_shrunk_without_absorber_kept`, событие с 2026‑08‑03) и принят.
Слияние не повторилось — модель ответила иначе.

`translation_quality_status` pass → warn — не регрессия озвучки: канал гигиены начал
работать на audiobook-прогонах в `c07f98f` (2026‑08‑10), то есть после прогона-базы. Три
причины: `unmapped_source_paragraphs_above_advisory_threshold`,
`false_fragment_headings_review_required`, `untranslated_body_text_review_required`
(12 строк, 25 760 символов английского в DOCX: восемь `omitted` сносок плюс
библиография и рекламная страница задней обложки — их нет в `processed_paragraph_registry`, в маркерную обработку они не входили).

## Что на экране

| уведомление | ключ | параметры | якорей |
|---|---|---|---:|
| озвучка | `result.narration_omitted_paragraphs_excluded_with_unanchored` | `{count: 8, chars: 5987, unanchored: 3}` | 5 |
| озвучка | `result.narration_review_data` | `{count: 4, rules: inline_citation}` | — |
| документ | `result.source_text_delivered_all_addresses_in_narration` | `{count: 8, blocks: 3, chars: 5987, elsewhere: 8}` | 0 |

Арифметика закрывается: 8 = 5 + 3, документ отсылает все 8 к сообщению озвучки.

**Одно из трёх «без адреса» — ложное.** `p0808` (1 378 символов, сноски главы) имеет
пригодный якорь в 75 символов — `Footnotes 1 Quoted in Naomi Klein, No Logo: Taking Aim at
the Brand Bullies (2000), p.325.` — и он в доставленном тексте есть. Отбрасывается он
проверкой «есть ли якорь в доставленном тексте»
(`src/docxaicorrector/pipeline/quality_gate.py:2299-2302`), потому что доставленный
Markdown нормализуется ЦЕЛИКОМ (`:2266-2270`), и снятие выделения
`_strip_narration_inline_emphasis` на всём документе спаривает звёздочки иначе, чем на
одном абзаце: в нормализованном документе остаётся `Klein, *No Logo: … Bullies (2000)` с
висящей `*`, а якорь — без неё. Воспроизведено на записях отчёта импортом тех же функций.
Честно непригодных здесь два (`«10»`, `«13»`), а не три.

Якорь `p0809` — `Reinhart et al.` (15 символов): делитель предложений лестницы режет на
сокращении `et al.`. Поиск по нему найдёт строку, но короткую и, вероятно, не
единственную.

## Чего в сводке нет

`run_summary.txt` не печатает `paragraph_disposition_counts`, счётчики FR-008
`narration_artifact.excluded_omitted_paragraph_count`/`_chars` и счётчики FR-017
`postprocess_paragraph_shortfall_*`: они есть только в отчёте. Список полей —
`tests/artifacts/real_document_pipeline/run_lietaer_validation.py:4479-4491` и
`:4498-4508`. Числа этих строк в таблицах выше взяты из `report.json`.
`postprocess_paragraph_shortfall_group_count`/`_paragraph_count` = 0 / 0: прогон
standalone, пост-прохода не было, проверка FR-017 здесь неприменима.
