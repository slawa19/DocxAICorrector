# Аудиокнига: четыре книги корпуса после спеки 061 — сравнение с 2026-08-06

Прогон: 2026-11-07, `main` = `769dfac` (слияние спеки 061), `processing_operation = "audiobook"`,
профиль `ui-parity-standalone-audiobook`, en → ru, маркеры включены, reader cleanup выключен,
модель — репозиторный дефолт `openrouter:google/gemini-3.1-flash-lite-preview`. Книги шли по
одной, через `scripts/run-real-document-validation.sh` под WSL. База — прогон 2026-08-06 на
`a633db8`, `artifacts/audiobook_four_book_run/`.

Это пункт 6 «Порядка исполнения» `specs/061-source-ships-under-green/spec.md`: единственный
прогон, на котором определён SC-001, и единственный шанс увидеть FR-001 в производстве (SC-002 б).

`git_head=None` в сводках — прогоны шли из бокового worktree, где git под WSL не читает
`.git`-файл; код — `769dfac`.

## Где что лежит

| книга | run id | папка |
|---|---|---|
| Money & Sustainability | `20261107T_061_audio_money` | `artifacts/audio_path_run_2026-11-07/money_sustainability/` (прогон одной книги, НЕ повторялся) |
| Creating Wealth | `20261107T_061_audio_creating_wealth` | `creating_wealth/` |
| Rethinking Money | `20261107T_061_audio_rethinking_money` | `rethinking_money/` |
| The Value of Everything | `20261107T_061_audio_value_of_everything` | `value_of_everything/` |

В каждой папке: `run_summary.txt` (копия сводки), `result_notices.json`
(`runtime.state.latest_result_notices`), `source_text_paragraphs.json` (абзацы со статусом
`omitted`/`source_restored` из `processed_paragraph_registry`, форма
`{block_index, paragraph_id, paragraph_status, text}`), `tts_excerpt_first40.txt` и
`stats.json` — вывод скрипта замера ниже по этой книге. Полные отчёты (27–40 МБ) и `.tts.txt`
остаются в `tests/artifacts/real_document_pipeline/runs/<run id>/` и в git не едут.

## 1. По книгам: до / после

`до` — 2026-08-06 (`artifacts/audiobook_four_book_run/*/run_summary.txt` и таблицы его
`comparison.md` §1); `после` — 2026-11-07. Лестницы деградации, `api_path_counts`,
`marker_chunk_merge_retry_count` и счётчиков удержания `omitted` 2026-08-06 ещё не было — «—».

| величина | Money до | Money после | CW до | CW после | RM до | RM после | VoE до | VoE после |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| вызовов модели | 311 | 310 | 385 | 385 | 257 | 246 | 195 | 219 |
| цена, $ | 0.523165 | 0.496948 | 0.573992 | 0.552772 | 0.514525 | 0.422178 | 0.456961 | 0.441038 |
| длительность, с | 783 | 652 | 831 | 706 | 862 | 606 | 910 | 755 |
| `accepted` | 1300 | 1310 | 1519 | 1518 | 2185 | 1727 | 1247 | 1277 |
| `omitted` | 13 | 8 | 0 | 0 | 0 | 0 | 0 | 0 |
| `source_restored` | 5 | 0 | 0 | **1** | 2 | **9** | 0 | 0 |
| отбраковки `marker_chunk_collapse` | 0 | 0 | 0 | 0 | 1 | 0 | 0 | 0 |
| прочие отбраковки | `marker_validation_source_fallback` 2 | — | — | `marker_validation_source_fallback` 1 | — | `non_completed_response_source_fallback` 1 | — | — |
| `marker_chunk_merge_retry_count` | — | 0 | — | 0 | — | 0 | — | 0 |
| ретраев всего | 32 | 25 | 8 | 7 | 10 | 17 | 1 | 4 |
| лестница: блоков / вызовов | — | 2 / 6 | — | 1 / 1 | — | 1 / 2 | — | 0 / 0 |
| доля лестницы | — | 1,94 % | — | 0,26 % | — | 0,81 % | — | 0 % |
| озвучка: исключено блоков подстановки / символов | 2 / 5581 | 0 / 0 | 0 / 0 | 1 / 24 | 0 / 0 | 1 / 1710 | 0 / 0 | 0 / 0 |
| озвучка: удержано `omitted` абзацев / символов | — | 8 / 5987 | — | 0 / 0 | — | 0 / 0 | — | 0 / 0 |
| `narration_excluded_blocks` | 59 | 59 | 66 | 66 | 58 | 78 | 519 | 491 |
| `narration_char_count` | 454 626 | 467 958 | 511 180 | 506 064 | 511 630 | 454 291 | 647 416 | 648 544 |
| `api_path_counts` | — | responses 310 | — | responses 385 | — | responses 246 | — | responses 219 |
| приёмка (прогонщик) | False | **True** | False | False | False | False | False | **True** |

Причины ретраев «после»: Money `marker_validation` 20, `recovery_after_exhausted_retries` 5;
CW `marker_validation` 5, `recovery…` 2; RM `marker_validation` 10, `incomplete_response` 3,
`non_completed_response` 2, `recovery…` 2; VoE `marker_validation` 2, `incomplete_response` 1,
`recovery…` 1.

Проваленные проверки приёмки «после»: CW — `untranslated_prose_not_delivered`,
`key_headings_preserved` (`creating_wealth/run_summary.txt:94`); RM —
`untranslated_prose_not_delivered` (`rethinking_money/run_summary.txt:94`). На экране (вердикт
внутри приложения, `translation_quality_report.acceptance_verdict`) у CW только одна проверка —
`untranslated_prose_not_delivered`: `key_headings_preserved` есть лишь у прогонщика, ему нужен
список ожидаемых заголовков из профиля корпуса, которого у приложения нет.

## 2. Итого по четырём книгам

| величина | до | после |
|---|---:|---:|
| вызовов модели | 1148 | 1160 |
| цена, $ | 2.068643 | **1.912936** |
| `accepted` / `omitted` / `source_restored` | 6251 / 13 / 7 | 5832 / 8 / 10 |
| отбраковки `marker_chunk_collapse` | 1 | **0** |
| `marker_chunk_merge_retry_count` | — | **0** |
| ретраев | 51 | 53 |
| лестница: блоков / вызовов / доля | — | 4 / 9 / **0,78 %** |
| озвучка: исключено блоков подстановки / символов | 2 / 5581 | 2 / 1734 |
| `narration_char_count` | 2 124 852 | 2 076 857 |
| приёмка прошла | 0 из 4 | 2 из 4 |

Цена «после» — сумма `cost_usd_reported_by_provider` четырёх реестров, у всех
`cost_accounting_complete=True`. Из неё платными в этой сессии были три книги ($1.415988);
Money оплачен раньше тем же днём.

## 3. Критерии спеки 061 на четырёх книгах

| критерий | замерено | вердикт |
|---|---|---|
| SC-001 (а): `source_restored`, произнесённых в `.tts.txt`, = 0 | В реестре 10 (`CW` 1, `RM` 9); ни один не найден в `.tts.txt` ни по первым 60 символам, ни по первым 40 символам со снятой разметкой. Озвучка исключила оба блока подстановки (1 / 24 и 1 / 1710 символов). | **PASS** |
| SC-001 (б): строк с нулевой долей кириллицы вне аппарата = 0 | 32 строки на четырёх книгах (Money 1, CW 5, RM 26, VoE 0). 27 — аппарат: титул `(i)` (Money), 25 строк предметного указателя и подпись `2c` внутри схемы (RM). **5 — вне аппарата (CW):** заголовки `B2B`, `B2C`, `C2C`, `C2B` (`p1339`, `p1342`, `p1344`, `p1346`) и `Barter Systems Inc.` (`p1511`), все `accepted`. | **по букве FAIL (5); по смыслу PASS** — это не текст исходника, а аббревиатуры и имя компании, которые по-русски пишутся латиницей. Ни одной строки с долей кириллицы между 0 и 50 %, кроме трёх в CW (адреса сайтов и `Systems Inc., 1991 год)`). |
| SC-002 (а): `marker_chunk_collapse` на первой попытке не доставляет исходник | отбраковок `marker_chunk_collapse` 0 на всех четырёх | **PASS** |
| SC-002 (б): `marker_chunk_merge_retry_count ≥ 1` там, где раньше был discard | 0 на всех четырёх; среди 49 отклонённых попыток нет ни одной `merged_marker_chunk` | **НЕ ПРОВЕРЕНО** — слияний не было |
| SC-003: доля вызовов FR-001 ≤ 0,98 % | 0 / 1160 = 0 % | **PASS, вакуумно** |

Отклонённые попытки по кодам (окно времени каждого прогона в `.run/app.log`): Money —
`paragraph_split_detected` 17, `empty_marker_chunk` 8, `unexpected_prefix` 2; CW —
`paragraph_split_detected` 8; RM — `paragraph_split_detected` 7, `marker_order_or_identity` 3,
`unexpected_prefix` 1; VoE — `marker_order_or_identity` 3. Код `merged_marker_chunk` пишется
ровно этим именем (`src/docxaicorrector/generation/_generation.py:314`, `:2306`), так что ноль —
не промах поиска. Ближайшие к слиянию события — сжатие абзаца без поглотившего соседа
(`marker_chunk_shrunk_without_absorber_kept`): Money 5, RM 1; оно по-прежнему принимается без
переспроса.

**Anti-regression лестницы** («стоимость на прогоне ≤ измеренной», 0,98 %): по четырём книгам
вместе 9 / 1160 = 0,78 % — выполнено; по одной книге Money 1,94 % — нет (два блока против
одного 2026‑08‑08, по три вызова на блок в обоих случаях).

### Скрипт SC-001

Запуск под WSL `python3 -I book.py <run_dir> .run/app.log <out_dir>`; часть, считающая строки, —
та же, что в `artifacts/audio_path_run_2026-11-07/money_sustainability/README.md`:

```python
TAG = re.compile(r"\[[^\[\]\n]{1,40}\]")          # теги озвучки латинские по построению
def share(s):
    ls = [ch for ch in s if ch.isalpha()]
    if not ls: return None
    return sum(1 for ch in ls if "CYRILLIC" in unicodedata.name(ch, "")) / len(ls)
for no, line in enumerate(lines, 1):
    sp = TAG.sub("", line); sh = share(sp)
    if sh is None: continue
    counted += 1
    if sh == 0: zero.append([no, sp.strip()[:160]])
    elif sh < 0.5: low.append([no, round(sh, 3), sp.strip()[:160]])
```

| книга | строк `.tts.txt` | с буквами | доля 0 | 0 < доля < 0,5 |
|---|---:|---:|---:|---:|
| Money & Sustainability | 2613 | 1292 | 1 | 0 |
| Creating Wealth | 2985 | 1492 | 5 | 3 |
| Rethinking Money | 3453 | 1721 | 26 | 0 |
| The Value of Everything | 2485 | 1242 | 0 | 0 |

Строки поимённо — `sc001.zero` в `stats.json` каждой книги. Отнесение к аппарату — моё, по
положению (титул; строки после заголовка указателя; подпись внутри схемы «Процесс создания
Терры»), а не по полю региона: регион абзаца в отчёт не пишется.

## 4. Откуда исходник в двух книгах — не слияние

- **Creating Wealth, блок 63, `p0204` `### False Assumption #2:`** (24 символа). Однопараграфный
  блок трижды разбит моделью (`paragraph_split_detected`), recovery — тоже; лестница — один
  вызов, абзац не спасён (`degradation_ladder_unrescued_paragraph_count=1`); подстановка блока
  (`markdown_marker_validation_source_fallback`). В DOCX — английский заголовок, в озвучке его
  нет (предыдущий «Ложное допущение номер один» звучит, второго заголовка слушатель не
  услышит). Вердикт приёмки — не пройдена (`untranslated_prose_not_delivered`), на экране
  `result.acceptance_not_passed`.
- **Rethinking Money, блок 5 — страница copyright** (9 абзацев, 1 710 символов: адрес
  издательства, телефоны, «All rights reserved»). Три ответа подряд со
  `response_status: "failed"` (`non_completed_response`) — подстановка блока
  (`markdown_non_completed_response_source_fallback`). Лестница на этот путь не заходит: на
  соседнем блоке 3 с `incomplete_response` она сработала и спасла 2 из 2 абзацев за 2 вызова.
  Блок посчитан как непереведённая ПРОЗА (`untranslated_prose_block_delivery_count=1`), и
  приёмка не прошла, хотя по содержанию это front matter. Регион блока в отчёт не пишется,
  поэтому, ошибка ли это детектора front matter или страница действительно попала в прозу,
  отсюда не установить. Направление ошибки — защитное: исходник не прошёл под зелёным
  статусом.

## 5. Что на экране

| книга | уведомления (`message_key` и параметры, якорей) |
|---|---|
| Money | `narration_omitted_paragraphs_excluded_with_unanchored` `{8, 5987, unanchored 3}` 5; `narration_review_data` `{4, inline_citation}`; `source_text_delivered_all_addresses_in_narration` `{8, 3 блока, 5987, elsewhere 8}` |
| CW | `narration_source_fallback_excluded` `{1, 24}` 1; `narration_review_data` `{2, inline_citation}`; `source_text_delivered_all_addresses_in_narration` `{1, 1 блок, 24, elsewhere 1}`; `acceptance_not_passed` `{1}` |
| RM | `narration_source_fallback_excluded` `{1, 1710}` 8; `source_text_delivered_all_addresses_in_narration` `{9, 1 блок, 1694, elsewhere 9}`; `acceptance_not_passed` `{1}` |
| VoE | `narration_review_data` `{1, disallowed_tags}` |

Числа сходятся с реестрами: каждый абзац с текстом исходника назван ровно в одном сообщении,
документ отсылает к озвучке. Две шероховатости адресов:

- Money: у `p0808` пригодный якорь в 75 символов посчитан «без адреса» — нормализация всего
  доставленного Markdown разом (`src/docxaicorrector/pipeline/quality_gate.py:2266-2270`)
  спаривает звёздочки выделения иначе, чем на одном абзаце, и проверка «якорь есть в тексте»
  (`:2299-2302`) промахивается. Подробно — README прогона одной книги.
- Делитель предложений режет на сокращениях: `Reinhart et al.` (Money), `Orders by U.S.` (RM).

Расхождение 1 710 / 1 694 символов в RM — разные единицы: блок целиком против суммы девяти
абзацев.

## 6. Что изменилось помимо спеки 061 и не объяснено здесь

- **Rethinking Money: `accepted` 2185 → 1727, `narration_excluded_blocks` 58 → 78, озвучка
  −57 тыс. символов** при том же числе абзацев источника (2265). Одна причина на всё: из 305
  блоков 78 не имеют записей в `processed_paragraph_registry` — 55 картинок и 23 блока
  примечаний и библиографии (58 432 символа, английский), которые теперь идут мимо модели
  как регион ссылок и исключаются из озвучки. 2026-08-06 `reference_region` на этой книге не
  срабатывал ни разу (`artifacts/audiobook_four_book_run/comparison.md`, §5), и эти абзацы
  переводились и звучали. Падение `accepted` — не потеря перевода прозы.
- **Предметный указатель Rethinking Money по-прежнему звучит**: блок 252 переведён и в реестре
  есть; 25 из 26 строк с нулевой долей кириллицы — его записи вида `Bell Telephone, 96`.
- **Приёмка прошла на Money и VoE.** Проверки структуры, ронявшие все четыре книги
  2026-08-06 (`key_headings_preserved`, `false_fragment_headings_present`,
  `mixed_script_terms_present`), на этих двух книгах проходят; это работа после `a633db8`, не
  спеки 061.
- **`translation_quality_status=warn` на всех четырёх.** Канал гигиены работает на
  audiobook-прогонах только с `c07f98f` (2026-08-10), так что прямого сравнения с базой нет.

## 7. Сводка не печатает

`run_summary.txt` не несёт `paragraph_disposition_counts`, удержание `omitted` из озвучки
(FR-008) и счётчики пост-прохода (FR-017) —
`tests/artifacts/real_document_pipeline/run_lietaer_validation.py:4479-4491`, `:4498-4508`.
Эти числа выше взяты из `report.json` (они же в `stats.json`).
`postprocess_paragraph_shortfall_*` = 0 на всех четырёх: прогоны standalone, пост-прохода не
было, проверка FR-017 здесь неприменима.
