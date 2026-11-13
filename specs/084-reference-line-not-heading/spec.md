# Feature Specification: Первая строка записи списка ссылок с висячим отступом — не заголовок

**Feature Branch**: `084-reference-line-not-heading`

**Created**: 2026-11-13

**Date**: 2026-11-13 (строки кода — ветка `084-reference-line-not-heading` от `main` @ `1712332`; номера строк «до» —
`main` @ `1712332`, «после» — эта ветка; замеры — производственным кодом обеих сторон на кэшированных спанах pdfminer
четырёх книг корпуса и полными подготовками audiobook / translate без модели. Данные вне git — `D:\Temp\claude\work-084\`:
`rep1.py`…`rep3.py` (отчёт прогона), `trace1.py` / `trace2.py` (спаны, сигнатуры, проходы), `imp.py` → `imp_base.json` /
`imp_new.json`, `diff_imp.py` → `diff_imp.txt`, `ana1.py` / `ana2.py` → `ana1_base.txt` / `ana2_base.txt` (формы
заголовков), `spanlvl.py` / `spanlvl2.py` → `spanlvl_base.txt` / `spanlvl2_base.txt` (условия на уровне строк),
`d2x.py` + `run_d2.sh` → `dump_{base,new}_{audiobook,translate}\`, `cmp_dump.py` → `cmp_audiobook.txt` /
`cmp_translate.txt`, `jobs_around.py`, `regcount.py` → `heads_base.txt` / `heads_new.txt`, `dbg_blocks.py`,
`mutate.py` → `mutation_results.txt`; базовая копия кода — `work-084\base\src` = `main` @ `1712332`)

**Status**: **IMPLEMENTED (2026-11-13) — правило в ветке `084-reference-line-not-heading`, тесты
`tests/test_pdf_reference_line_not_heading.py`; приёмочное ревью Codex, слияние в `main` и полный прогон в главном
дереве — за оркестратором.** Платный прогон не повторялся: что гейт больше не увидит эти строки заголовками, показано
трассировкой без модели (раздел 5). Spec-only tier (Конституция III): объём ограничен одной измеренной причиной,
проверка — детерминированные тесты и офлайн-замер на корпусе; `plan.md` и `tasks.md` не пишутся.

**Owner surface**: `pdf_import/logical_import.py` — путь типографского заголовка: `_classify_span_role` (`:685-745`,
новый параметр `page_lines`), `_looks_like_pdf_heading_candidate` (`:1624-1671`, вызов правила `:1646-1652`), новое
правило `_opens_a_wrapped_citation_entry` (`:1582-1621`); цикл спанов `build_paragraph_units_from_text_spans` (строки
страниц `:178-182`, передача `:273`); выделенный из спеки 081 помощник `_line_wraps_to_the_hanging_indent`
(`:4166-4182`; `_entry_line_sits_at_the_hanging_indent` `:4130-4163` теперь зовёт его, поведение то же). Пути кода —
относительно `src/docxaicorrector/`.

**Companion**: `specs/081-entry-hanging-indent/spec.md` (тест серии висячего отступа, который правило переиспользует);
спека 064 FR-006 и правило 12 промпта перевода (модель оставляет ссылки как есть; кредит аппарата —
`pipeline/block_execution.py:611-724`); `specs/083-gate-bibliography-form/spec.md` (гейт непереведённого тела).

## Проваленный прогон (дословно)

Прогон `20261113T_q_creatingwealth` (2026-11-13, код `main` @ `07f26fe`), профиль `creatingwealth-pdf-full-benchmark`,
run profile `ui-parity-translate-benchmark-quality`; архив — `D:\Temp\claude\runs-2026-11-13\creatingwealth\translate\`.
`result=succeeded`, `status=failed`. Сводка (`creatingwealth_pdf_full_benchmark_summary.txt`):

```
acceptance_passed=False
acceptance_failed_checks=untranslated_prose_not_delivered,key_headings_preserved
```

Отчёт (`creatingwealth_pdf_full_benchmark_report.json`, ключ `acceptance`):

```json
"failed_checks": ["untranslated_prose_not_delivered", "key_headings_preserved"]
```

Производственный вердикт (`translation_quality_report.acceptance_verdict.failed_checks`) —
`["untranslated_prose_not_delivered"]`: `key_headings_preserved` — проверка харнесса
(`tests/artifacts/real_document_pipeline/run_lietaer_validation.py:6031-6037`), production её не считает.

| Проверка | actual | threshold | превышение |
| --- | --- | --- | --- |
| `untranslated_prose_not_delivered` | `untranslated_prose_block_delivery_count` = 1, `…_chars` = 113 | 0 блоков, либо весь объём < `anchor_min_visible_chars` = 3 (`validation/acceptance.py:952-959`) | 1 блок при допуске 0; 113 символов при пороге 3 (×37,7) |
| `key_headings_preserved` | `demoted_heading_count` = 1 | 0 (`run_lietaer_validation.py:6033`) | 1 при допуске 0 |

Обе проверки дословно (`acceptance.checks`):

```json
{"name": "untranslated_prose_not_delivered", "passed": false, "applicable": true,
 "untranslated_prose_block_delivery_count": 1, "untranslated_prose_block_delivery_chars": 113,
 "untranslated_prose_below_anchor_floor": false, "anchor_min_visible_chars": 3,
 "untranslated_prose_block_delivery_kind_counts": {"source_text_fallback": 1},
 "controlled_block_fallback_block_count": 1}
{"name": "key_headings_preserved", "passed": false, "applicable": true,
 "source_heading_count": 260, "mapped_source_heading_count": 256, "unmapped_source_heading_count": 4,
 "demoted_heading_count": 1, "demoted_heading_scope": "main_content_span", "heading_level_shift_count": 0,
 "demoted_samples": [{"paragraph_id": "p1538", "source_index": 1538, "mapped_target_index": 1521,
   "source_role": "heading", "source_structural_role": "heading", "source_heading_level": 3,
   "text_preview": "hazel, henderson. ethical markets: growing the green economy (vermont: chelsea green",
   "target_text_preview": "hazel, henderson. ethical markets: growing the green economy (vermont: chelsea green publishing. 2006)",
   "target_style_name": "Body Text", "reason": "content_survived_but_heading_demoted"}]}
```

Событие блока (`events.jsonl:1193`; `block_index` в событиях считается с 1 — блок 1 это `[[DOCX_IMAGE_img_001]]`, так что
блок 407 — задание 406 подготовки):

```json
{"event_id": "block_untranslated_prose_delivered", "block_index": 407, "block_count": 438,
 "rejection_kind": "source_text_fallback", "delivered_chars": 113, "paragraph_count": 2, "prose_paragraph_count": 2,
 "input_preview": "### Hazel, Henderson. *Paradigms in Progress: Life Beyond Economics* (Indianapolis: Knowledge\n\nSystems Inc. 1991)"}
```

Модель вернула блок неизменным (артефакт `block_407_056a7aeb.json`: `processed_chunk_preview` = `target_text_preview`) —
по правилу 12 промпта ссылку оставляют как есть, и это верно; но абзацы блока лежат в регионе `prose` (заголовок
«Resources» не входит в словарь разделов литературы), кредита аппарата спеки 064 FR-006 нет, и правило пары спеки 059
читает неизменный блок как `source_text_fallback`. В блоке 408 (задание 407) модель слила «Publishing. 2006)» с
заголовком p1538 и сняла с него `###` — это и есть понижение, которое считает `key_headings_preserved`.

**Четыре несопоставленных заголовка** (`formatting_diagnostics[0].source_registry`, `mapped_target_index` = null; данные
ревью, не провал — `run_lietaer_validation.py:3958-3963`), прочитаны по выводу прогона:

| id | текст источника | что это | что стало в выводе |
| --- | --- | --- | --- |
| p0028 | «preface by dennis meadows» | заголовок титульной страницы (front matter) | слит моделью в строку «…Предисловие Денниса Медоуза Вступительное слово Хантер Ловинс» (`.md:49`) |
| p1255 | «6 months - 1 year broad cros s s ection of the public» | ячейка таблицы (с разрывами букв импорта), типизированная заголовком | «6 месяцев — 1 год Широкие слои общественности» (`.md:2489`) |
| p1382 | «social purpose currencies» | настоящий подзаголовок | слит моделью в конец предыдущего абзаца «…Вот несколько примеров: Валюты социального назначения» (`.md:2739`) |
| p1789 | «2604 pounds of solid waste» | пункт «Environmental Benefits Statement» на последней странице, типизированный заголовком | слит в абзац (`.md:3541`) |

Ни один из четырёх — не запись списка ссылок, и правило этой спеки ни одного из них не меняет (раздел 4).

## Причина (file:line, `main` @ `1712332`)

CW стр. 155, раздел «Resources» (регион `prose`). Тело книги — 14,5 pt, левый край тела `body_left_x0` = 5,0, интерлиньяж
16,56. Список набран висячим отступом: первая строка записи — x0 = 33,8, перенесённые — x0 = 48,2; кегль 14,4.

| строка (top) | x0 / x1 | начертание | роль на `main` | почему |
| --- | --- | --- | --- | --- |
| «Barter Systems, Inc website. [online]. [cited December 28, 2010]. …» (206,9) | 33,8 / 576,4 | обычное | body | инвариант цитаты: `[online]` и год с запятой в самой строке |
| «Colin Harrison. Project Proposal: CyberTroc — … Society.» (256,6) | 33,8 / 580,4 | курсив | body | кончается точкой (`_has_terminal_sentence_punctuation`, `:1587`) |
| **«Hazel, Henderson. Paradigms in Progress: Life Beyond Economics (Indianapolis: Knowledge»** (322,8) | 33,8 / 580,3 | курсив | **heading 3** | см. ниже |
| «Systems Inc. 1991)» (339,4) | 48,2 / 158,1 | обычное | body | |
| **«Hazel, Henderson. Ethical Markets: Growing the Green Economy (Vermont: Chelsea Green»** (355,9) | 33,8 / 569,6 | обычное | **heading 3** | см. ниже |
| «Publishing. 2006)» (372,5) | 48,2 / 151,7 | обычное | body | |
| «Mutual Credit Systems» (417,8) | 239,4 / 372,5 | обычное, по центру | heading | настоящий подзаголовок группы |
| **«Thomas H. Greco, Jr. “Chapter 12: … Mutual Credit Systems.”»** (434,4) | 33,8 / 598,3 | обычное | heading → слит | см. ниже |

1. **Свидетельство заголовка, которое сработало.** `_classify_span_role` (`:730-736`) → `_looks_like_pdf_heading_candidate`
   (`:1574-1613`). Сигнатура обеих строк Hazel: `font_ratio` 0,993, `indent_units` 1,74 (33,8 против левого края тела 5,0
   в единицах интерлиньяжа), `title_delta` 0,84 / 0,85, `isolation_units` 0,26. Ближайший кластер стилей — № 4 (411
   строк, центр `indent` 2,34 — это кластер всех отступленных строк книги), и `_select_heading_clusters`
   (`:1343-1367`) взял его в заголовочные; опора — `_signature_has_heading_support` `:1444` («отступ ≥ 1 интерлиньяж и
   доля слов с заглавной ≥ 0,45»). Запись литературы — это имена и слова названия с заглавной, так что «регистр
   заголовка» у неё есть всегда.
2. **Что должно было остановить и почему не остановило.** Инвариант `_looks_like_footnote_or_citation_tail`
   (`:1560-1571`, вызов `:1472`) не даёт заголовком строку, которая цитирует (`[online]`, адрес, год с запятой / скобкой /
   двоеточием), — но читает **одну строку**. У обеих записей Hazel год и закрывающая скобка («1991)», «2006)») ушли на
   перенесённую строку. У соседних записей год или `[online]` стоят в первой строке — потому соседи и остаются телом.
3. **Третье следствие той же ошибки — потерян настоящий заголовок.** Строка Greco прошла тем же путём (кончается на
   «.”», `[online]` и год — на перенесённой строке), `_can_merge_heading_span` (`:3393-3419`) приклеил её к
   центрированному заголовку «Mutual Credit Systems» над ней (зазор 2,2 pt), а `_paragraph_from_heading_spans`
   (`:3619-3620`, `_looks_like_glued_heading_line`) превратил склейку в **один абзац тела**: «Mutual Credit Systems Thomas
   H. Greco, …» (p1540 прогона). В выводе модель сама сделала из него «### Системы взаимного кредита Thomas H. Greco…».
4. **Почему это не поймано в разделе литературы.** Заголовок «Resources» не входит в словарь названий разделов
   (`_BACK_MATTER_SECTION_KIND_BY_TITLE`), регион — `prose`; ни расстановка ролей раздела (спека 065 FR-008), ни
   склейка R-7 / 081, ни кредит аппарата (064 FR-006) этот список не видят.

**Посылка брифа подтверждена**: обе строки — типизированные заголовком записи списка ссылок; дефект импорта, не
перевода; спека 081 тут ни при чём (регион не back matter), и на `main` до 081 картина та же (`verify078\` и
`verify081\` дампы оркестратора). **Уточнение к посылке**: виновата не строка-заголовок как таковая, а то, что
инвариант цитаты читает одну строку из двух; и та же ошибка тихо стёрла настоящий заголовок «Mutual Credit Systems».

## Что измерено (2026-11-13)

### 1. Существующие тесты формы на всех заголовках четырёх книг (`ana2_base.txt`, `ana1_base.txt`)

Единицы импорта `main` @ `1712332`, роль `heading`, 687 штук. Тесты формы `pipeline/output_validation.py`:
`is_citation_form_paragraph` (`:572`), `notes_run_piece_reads_as_reference` (`:789`), `has_hard_reference_mark`
(`:679`) — по тексту самого заголовка; «серия ссылок» — предыдущая и следующая единицы читаются как ссылка
(`is_citation_form_paragraph`).

| Условие | RM (147) | VoE (112) | Money (169) | CW (259) | всего (687) |
| --- | ---: | ---: | ---: | ---: | ---: |
| `is_citation_form_paragraph` (свой текст) | 2 | 5 | 8 | 4 | 19 |
| `notes_run_piece_reads_as_reference` (свой текст) | 0 | 0 | 7 | 1 | 8 |
| `has_hard_reference_mark` (свой текст) | 0 | 0 | 2 | 0 | 2 |
| серия: сосед сверху и снизу — ссылки | 5 | 8 | 1 | 9 | 23 |
| хоть одно из четырёх | 7 | 13 | 11 | 13 | 44 |

Все 44 прочитаны. **Запись ссылки, ошибочно ставшая заголовком — 1** (CW Hazel «Ethical Markets…», только по серии;
вторая запись Hazel не ловится ни одним из четырёх: её собственный текст не цитирует, сосед сверху «[online]…» по форме
не ссылка). **Настоящих заголовков — 36**: RM «Chapter 1/4/5/7», «BIBLIOGRAPHY»; VoE «Karl Marx on ‘Production’ Labour»,
«THE RISE OF THE ‘NEOCLASSICALS’», «FINANCE AND THE ‘REAL’ ECONOMY», «THE RETREAT OF ‘PATIENT’ CAPITAL», «INTRODUCTION:
MAKING VERSUS TAKING», «2.»…«7.» (подписи глав в примечаниях), «Bibliography»; Money «The ‘Service Function’ Paradigm…»,
«The Monetary ‘Blind Spot’», «1. The Emergence of a ‘Global Casino’», «Box 5.4 – The Ele ve nth Round», «7. The ‘Chicago
Plan’», «1. Doraland: Creating a ‘Learning Country’», «4. C3: ‘Commercial Credit Circuits’…», «Acknowledgements»; CW
«False Assumption #1:», «#2:», «The “Free Market” System», «Local Currencies», «Chapter 2/5/8/9/10/12/13». **Прочее — 7**
(не ссылка и не заголовок, вне этой спеки): RM две строки формулы («= 200,000 Terras», «(Terra Operation Costs/time unit)
×»), VoE подпись эпиграфа («Big Bill Haywood, founder…¹»), Money подпись к рисунку («Fig ure 6.1: …»), два пункта схемы
со ссылкой на страницу («Torek es at city level p.168», «Civics at the city or regional level p.173»), CW подпись
«FIGURE A.1. …».

**Вывод: форма текста заголовка и серия соседей для правила непригодны** — на 1 найденную ссылку 36 настоящих
заголовков (кавычки в названии, «#», подписи глав в примечаниях). Правило «строка в серии ссылок и сама читается как
ссылка» (пример брифа) на корпусе срабатывает **0 раз**: у обеих строк Hazel собственный текст ссылкой по форме не
читается.

### 2. Условия на уровне строк (`spanlvl2_base.txt`)

Каждая строка, которую классификатор `main` типизирует заголовком через типографский путь
(`_looks_like_pdf_heading_candidate`), — 677 строк (RM 129, VoE 144, Money 154, CW 250); 19 заголовков Money решены
детерминированными путями и сюда не входят. «Следующая строка» — ближайшая строка содержимого
(`_nearest_content_span`).

| Условие (каждое отдельно) | RM | VoE | Money | CW | всего (677) |
| --- | ---: | ---: | ---: | ---: | ---: |
| H: следующая строка — на висячем отступе серии (`_line_wraps_to_the_hanging_indent`: шаг ≥ 0,45 интерлиньяжа вправо и ≥ 2 записей «поле → отступ» в непрерывной серии строк одного кегля на странице) | 0 | 0 | 0 | 3 | 3 |
| R: строке не хватило места для первого слова следующей (`_entry_line_ran_out_of_room`) | 53 | 39 | 15 | 6 | 113 |
| C: строка + следующая читаются как цитата (`_looks_like_footnote_or_citation_tail`) | 5 | 29 | 14 | 25 | 73 |
| **H ∧ R ∧ C (правило)** | **0** | **0** | **0** | **3** | **3** |

Три срабатывания — CW стр. 155: две строки Hazel и строка Greco. **Все три — первые строки записей списка ссылок.**
Сочетания без H проверены как отвергнутые варианты:

* **R ∧ C ∧ следующая строка подряд, того же кегля, не в заголовочном начертании, строка не крупнее тела** (вариант A,
  без серии) — 27: CW 3 (те же), Money 2 (подписи «Em. Prof. Dennis Meadows» + «New Hampshire, February 2012» и «Bernard
  Lietaer, Christian Arnsperger, …» + «M ay, 2012», выровненные вправо — «нехватка места» у выровненной вправо строки
  тривиальна), VoE 22 (строки записей в примечаниях, которые потом и так снимает с заголовка спека 065 FR-008). Настоящих
  заголовков среди 27 нет, но вариант трогает 24 места, где дефекта на выходе нет, и опирается на условия, которые
  ничего не говорят о списке. Отвергнут в пользу H.
* **Без R** (H ∧ C): на корпусе те же 3, но в прозе с красной строкой короткий заголовок у поля над строкой с отступом
  тоже стоит «в серии поле → отступ» (тест `…ran_out_of_room…`); без R такой заголовок с годом в первой строке абзаца
  был бы понижен.
* **Без C** (H ∧ R): на корпусе те же 3; держит глоссарий / перечень с висячим отступом без ссылок (тест `…citation…`).

Почти-попадания варианта A (не выполнено ровно одно его условие, `spanlvl_base.txt`): у центрированных подзаголовков
списка CW («Commercial Barter Systems», «LETS Systems», «Time Banks», «Local Currencies»), у 12 заголовков CW над
абзацем, чья первая строка несёт год («Redefining Wealth», «Calgary’s 100 Year Plan» и др.), у VoE «Governing Public
Value» и Money «Earning Wellness Tokens» выполнены все условия, кроме R, — их держит R (и H: следующая строка у них
левее или на том же x0). VoE «FROM OBJECTIVE TO SUBJECTIVE: A NEW THEORY OF VALUE BASED ON» + «PREFERENCES» (настоящий
двухстрочный заголовок) держит C.

### 3. Какое свидетельство делает строку заголовком и какая часть неверна

Заголовком по типографике строку делают: кегль выше тела (`font_ratio` ≥ 1,12), изоляция, отступ или граница
предложения вместе с регистром (`_signature_has_heading_support`, `:1437-1450`) и принадлежность к заголовочному кластеру.
Здесь сработало «отступ ≥ 1 интерлиньяж + регистр заголовка» — свидетельство, которое запись списка с висячим отступом
несёт по своей природе. Неверна не опора, а **граница чтения инварианта цитаты: одна строка вместо записи**.
Правило не ослабляет опору и не трогает кластеры: оно дочитывает запись на одну строку вниз только там, где страница
сама показывает, что следующая строка — перенос этой (H и R), и спрашивает тот же инвариант.

Направление ошибки. Ссылка, ставшая заголовком: провал гейта (обе проверки этого прогона), граница блока перевода, на
выходе — оборванная строка «### Hazel, Henderson. …(Indianapolis: Knowledge» заголовком 3-го уровня, а в этой книге и
**потерянный настоящий заголовок** «Mutual Credit Systems». Ложной главы в озвучке здесь не было: уровень 3 ниже уровня
глав плана озвучки CW (уровень 1, раздел 4). Настоящий заголовок, ставший телом: теряется навигация и граница главы
озвучки. Правило построено так, чтобы не делать ни того, ни другого на корпусе: 3 исправления, 0 потерянных настоящих
заголовков, 1 восстановленный.

## Решение и правило

`_opens_a_wrapped_citation_entry` (`logical_import.py:1582-1621`), спрашивается в `_looks_like_pdf_heading_candidate`
сразу после инвариантов (`:1646-1652`), то есть **только на типографском пути**: главы по шаблону («Chapter N») и
нумерованные заголовки разделов решаются раньше и до правила не доходят. Строка **не** становится заголовком, когда
выполнены все три:

1. **H** — следующая строка (ближайшая строка содержимого) переносится на висячий отступ серии: начинается правее строки
   на шаг красной строки (0,45 интерлиньяжа — шаг группировки строк, `_looks_like_body_paragraph_indent_boundary`), и
   непрерывная серия строк одного кегля на этой странице показывает пару «поле → отступ» не меньше
   `_HANGING_INDENT_MIN_RUN_ENTRIES` = 2 раз (`_hanging_indent_run_entry_count`, спека 081; помощник
   `_line_wraps_to_the_hanging_indent` выделен из `_entry_line_sits_at_the_hanging_indent` без изменения поведения).
   Серия ищется на странице строки — через разрыв страницы ничего не сравнивается;
2. **R** — строке не хватило места для первого слова следующей (`_entry_line_ran_out_of_room`, порог — правый край
   колонки тела, p85 правых краёв длинных строк);
3. **C** — строка и следующая вместе читаются как цитата по тому же инварианту `_looks_like_footnote_or_citation_tail`.

Ни одного нового числа: 0,45, 2, правый край колонки и инвариант цитаты — существующие величины импорта. Ни одного слова
из книги. Что строка станет телом — дальше решает обычная группировка строк; правило не склеивает и не режет.

## 4. До / после на корпусе (2026-11-13)

**Импорт** (`diff_imp.txt`, кэш спанов): RM, VoE, Money — единицы, роли и тексты те же. CW — единиц 1757 → 1756,
заголовков 259 → 258; изменения (полный список):

| до | после |
| --- | --- |
| body «[online]. [cited December 28, 2010]. ict- 21.ch/…doc. An article about CyberTroc, a type of internet-based barter system.» | body «…barter system. Hazel, Henderson. Paradigms in Progress: Life Beyond Economics (Indianapolis: Knowledge» |
| **heading 3** «Hazel, Henderson. Paradigms in Progress: … (Indianapolis: Knowledge» | (в абзаце выше) |
| body «Systems Inc. 1991)» | body «Systems Inc. 1991) Hazel, Henderson. Ethical Markets: … (Vermont: Chelsea Green» |
| **heading 3** «Hazel, Henderson. Ethical Markets: … (Vermont: Chelsea Green» | (в абзаце выше) |
| body «Mutual Credit Systems Thomas H. Greco, Jr. “Chapter 12: …”» | **heading 3** «Mutual Credit Systems» + body «Thomas H. Greco, Jr. “Chapter 12: …”» |

Минус две ссылки-заголовка, плюс один восстановленный настоящий заголовок.

**Подготовка audiobook** (`cmp_audiobook.txt`, полный пайплайн без модели): RM, VoE, Money — абзацы, роли, регионы,
пометки серий, причины исключения и тексты те же. CW: абзацев 1796 → 1795, заголовков (структурная роль) 252 → 251,
озвучиваемых 1493 → 1492 (два абзаца стали одним), озвучиваемый текст — тот же (без разметки `###` — те же символы
и тот же порядок слов на всех четырёх книгах; разница непробельных символов −3 — это разметка двух ушедших и одного
нового заголовка), пометки серий 1 → 1, регион всех затронутых абзацев `prose`,
причина исключения у всех `None` и до, и после. **План озвучки** (`build_narration_document_plan` на озвучиваемых
абзацах): уровень глав / Heading 1 / глав — RM (1, 22, 23), VoE (2, 13, 14), Money (1, 20, 20), CW (1, 19, 19) — **те
же**: заголовки Hazel были уровня 3, ниже уровня глав CW, ложной главы в озвучке они не давали.

**Подготовка translate** (`cmp_translate.txt`): RM, VoE, Money — то же самое. CW: абзацев 1796 → 1795, заданий 438 →
438, текст тот же без разметки `###` (те же символы, тот же порядок слов); заголовков 3-го уровня на один меньше
(минус две ссылки, плюс «Mutual Credit Systems»). Меняются три задания (номера — с 0):

| задание | до | после |
| --- | --- | --- |
| 405 | «### Commercial Barter Systems» + 3 записи, 495 симв. | то же + обе записи Hazel, 711 симв. |
| 406 | «### Hazel, Henderson. *Paradigms…* (Indianapolis: Knowledge» + «Systems Inc. 1991)», 113 симв. | «### Mutual Credit Systems», 25 симв. |
| 407 | «### Hazel, Henderson. *Ethical Markets…*» + «Publishing. 2006)» + «Mutual Credit Systems Thomas H. Greco…» + «*New Money…*» + «complementarycurrency.org.», 453 симв. | «Thomas H. Greco…» + «*New Money…*» + «complementarycurrency.org.», 320 симв. |

## 5. Гейт без модели

- **`key_headings_preserved`.** `source_heading_count` берётся из реестра формата — абзацы подготовки с `role ==
  "heading"` (`run_lietaer_validation.py:4046-4049`). Подготовка translate CW (`regcount.py`): **260 → 259**; из списка
  ушли обе строки Hazel, пришла «Mutual Credit Systems» (`heads_base.txt` / `heads_new.txt`). Понижение p1538 из
  `demoted_samples` невозможно: этого абзаца-заголовка больше нет. Новый заголовок стоит один в своём блоке; ответ из
  одного заголовка проходит `classify_processed_block` (у входа нет тела, `output_validation.py:393`), так что он
  доставляется заголовком — **прогноз**, проверяется следующим прогоном.
- **`untranslated_prose_not_delivered`.** Содержимое блока 407 прогона (задание 406) больше не отдельный блок: обе
  записи Hazel — в задании 405 вместе с заголовком «Commercial Barter Systems» и двумя аннотациями, которые модель в
  этом прогоне перевела («Лидер в индустрии коммерческого бартера…», «Статья о CyberTroc…», `.md:3031-3037`). Правило
  пары (`output_validation.py:421`) срабатывает только на блок, равный источнику целиком, — для задания 405 это
  возможно лишь если модель оставит непереведёнными и заголовок, и обе аннотации. **Остаточный риск, назван**:
  задание 407 «после» — три абзаца ссылок без заголовка в регионе `prose`; если модель вернёт его без изменений,
  блок снова станет `source_text_fallback`, и проверка снова упадёт — на другом блоке. В этом прогоне модель в том же
  абзаце «*New Money…* … Complementary Currency Resource Center website…» перевела «website» («Сайт Complementary
  Currency Resource Center», `.md:3047`), то есть ответ отличался от источника; это наблюдение, не гарантия. Корень
  риска — ссылки в регионе `prose` без кредита аппарата (Non-goals), не этот импорт.

## Requirements *(mandatory)*

- **FR-001**: Строка, для которой выполнены H, R и C, не становится заголовком по типографике.
- **FR-002**: Правило меняет только роль строки; текст не теряется и не переставляется (тест сохранения символов и
  порядка слов; на корпусе — непробельные символы импорта те же на всех четырёх книгах).
- **FR-003**: Детерминированные заголовки (шаблон главы, нумерованный заголовок раздела) правило не спрашивает (тесты
  маршрутизации).
- **FR-004**: Ни одной константы, подобранной под книгу, ни одного слова: только существующие геометрические величины и
  существующий инвариант (Конституция VII).

## Success Criteria *(mandatory)*

- **SC-001**: На CW обе строки Hazel больше не заголовки; источник `key_headings_preserved` (реестр подготовки
  translate, `role == heading`) — 260 → 259 (раздел 5).
- **SC-002**: На четырёх книгах ни один настоящий заголовок не потерян (раздел 4: на RM, VoE, Money импорт и обе
  подготовки побайтно те же; на CW из заголовков ушли только две строки Hazel).
- **SC-003**: Непробельные символы импорта и озвучиваемый текст подготовки — те же (раздел 4).
- **SC-004**: Каждое условие правила закреплено синтетическим тестом, падающим при его удалении (Changelog, мутации).

## Non-goals

- **Платный перепрогон перевода.** Не делается; вместо него трассировка гейта без модели (раздел 5). Остаточный риск
  гейта назван там же.
- **Правило по форме текста заголовка или по серии соседей-ссылок** (пример брифа). Измерено и отвергнуто: 36
  настоящих заголовков на 1 ссылку; правило «в серии и сама ссылка» не срабатывает ни разу (раздел 1).
- **Вариант без серии висячего отступа** (R ∧ C ∧ подряд ∧ кегль): 27 мест вместо 3, из них 24 без дефекта на выходе
  (раздел 2).
- **Добавить «Resources» в словарь разделов литературы.** Это список слов (Конституция VII); регион и кредит аппарата
  — отдельная тема.
- **Склейка записей этого списка.** Группировка строк CW склеивает соседние записи списка «Resources» друг с другом, если
  перенесённая строка не кончается знаком конца («Press 1987)» + следующая запись) — так было на `main` и с другими
  записями этого же списка («New Money … chp12.html. Complementary Currency Resource Center website…»). С правилом
  записи Hazel попадают в ту же группировку: «…a type of internet-based barter system. Hazel, Henderson. *Paradigms…*
  (Indianapolis: Knowledge» и «Systems Inc. 1991) Hazel, Henderson. *Ethical Markets…* (Vermont: Chelsea Green»
  (раздел 4). Символы не теряются; граница записи — дефект группировки строк, отдельная спека.
- **Запись, чей перенос ушёл на следующую страницу**, и **одинокая запись** (серия < 2 на странице) — правило их не
  решает, остаются как на `main` (тесты `…page_break…`, `…lone_wrapped_entry…`). На корпусе таких заголовков нет.
- **Название, которое кончается годом** («… of 1929»), читается импортом как строка оглавления с номером страницы
  (`_looks_like_toc_entry`) и становится телом ещё до этого правила — найдено при написании теста, на `main` так же;
  отдельный дефект, не строится здесь.
- **Сегменты подготовки** (`document/segments.py`): строка Greco, ставшая телом, открывает сегмент (жёсткая граница
  блока), потому заголовок «Mutual Credit Systems» стоит отдельным блоком (раздел 4). Не трогается: файл вне владения
  спеки.
- Уже переведённые DOCX / озвучки не переобрабатываются.

## Anti-regression

1. **Ни один символ не теряется** (требование владельца): тест `test_rule_conserves_every_character_and_the_word_order`;
   на корпусе непробельные символы импорта RM 430 118, VoE 626 779, Money 433 218, CW 449 835 — те же
   (`diff_imp.txt`); озвучиваемый текст подготовки audiobook тот же (раздел 4).
2. **Настоящие заголовки остаются заголовками** (`tests/test_pdf_reference_line_not_heading.py`): заголовок прямо над
   списком ссылок; заголовок во всю строку над абзацем, чья первая строка цитирует (держит H); короткий заголовок над
   прозой с красной строкой (держит R); перечень с висячим отступом без ссылок (держит C); нумерованный заголовок и
   «Chapter N» (маршрутизация); название главы с годом в дисплейном кегле над списком ссылок.
3. **Последствия ниже по течению**: строки, ставшие телом, не помечаются серией примечаний (тест
   `test_demoted_entries_are_not_marked_a_run_of_notes`; на корпусе пометки серий 0 / 0 / 17 / 1 — те же); главы плана
   озвучки — те же на всех четырёх книгах (раздел 4).
4. Существующие тесты импорта (`tests/test_pdf_text_layer_logical_import.py`, `tests/test_pdf_hanging_indent_note_lines.py`,
   `tests/test_pdf_hanging_indent_entry_lines.py`, `tests/test_paragraph_boundary_normalization.py`,
   `tests/test_processing_runtime.py`) проходят без изменений.
5. Полный прогон в главном дереве после слияния и пустой `git status --porcelain` перед «зелёным»; приёмочное ревью
   Codex по затронутым поверхностям — за оркестратором.

## Assumptions

- Кэш спанов `D:\Temp\claude\tear-study\spans_*.pkl` снят 2026-11-12; извлечение спанов
  (`pdf_import/text_layer_quality.py`) с тех пор не менялось (последний коммит — спека 067). Подготовки (раздел 4)
  считались из самих PDF, не из кэша.
- Базовая подготовка CW воспроизводит прогон: 1796 абзацев, 438 заданий, 260 заголовков в реестре — как в отчёте прогона
  (код `07f26fe` против `1712332` здесь не расходится).

## Changelog

- 2026-11-13 — **спека написана, правило реализовано, замеры** (скрипты и выводы — `D:\Temp\claude\work-084\`).
  - Причина найдена трассировкой спанов (`trace1.py`) и проходов импорта (`trace2.py`): разделы «Причина» и 1–3.
  - Импорт и подготовки до / после: разделы 4–5. На `main` и на ветке с выключенным правилом импорт один и тот же
    (тест `_rule_off` в каждом позитивном тесте; на корпусе база — копия `main` @ `1712332`).
  - **Мутации** (`mutate.py` → `mutation_results.txt`; каждая — замена одного фрагмента в `logical_import.py`, прогон
    `tests/test_pdf_reference_line_not_heading.py` и `tests/test_pdf_hanging_indent_entry_lines.py`, восстановление):

    | Мутация | Падает |
    | --- | --- |
    | M1 убрать H | `…run_of_two…`, `…hanging_run…full_width_heading…`, `…page_break…` |
    | M2 убрать R | `…ran_out_of_room…short_heading…` |
    | M3 убрать C | `…citation…does_not_cite…` |
    | M4 серия из одной записи | `…run_of_two…` (и 5 тестов 081) |
    | M5 убрать шаг 0,45 интерлиньяжа в общем помощнике | `test_line_at_the_margin_after_a_line_at_the_indent_starts_an_entry` (081) — шаг общий с 081 и закреплён её тестом |
    | M6 искать серию вместе со строкой следующей страницы | `…page_break…` |
    | M7 убрать вызов правила из классификатора | 5 позитивных тестов |
    | M8 не передавать строки страницы из цикла спанов | те же 5 |
  - Во время замера лог одного фонового запуска по ошибке записался в корень главного дерева
    (`D:\Work\Projects\DocxAICorrector\d2_new.log`); файл перенесён в `work-084`, `git status` главного дерева пуст.
