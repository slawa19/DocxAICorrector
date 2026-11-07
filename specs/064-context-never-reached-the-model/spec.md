# Feature Specification: Контекст документа никогда не доходил до модели, и ещё шесть дефектов, которые показал повторный прогон четырёх книг после спеки 063

**Feature Branch**: `[064-context-never-reached-the-model]`

**Created**: 2026-11-07

**Date**: 2026-11-07 (все строки кода проверены на `3bfadd6`, последнем коммите `main` на эту дату)

**Status**: **IN PROGRESS (2026-11-07) — спека написана по результатам повторного платного прогона
четырёх книг на коде спеки 063 (`aca048a`, `$2,39`, 1680 вызовов); правки R-1…R-7 в работе у
четырёх агентов в боковых worktree.** Spec-only tier (Конституция III): каждая правка ограничена
названной находкой прогона и проверяется детерминированным тестом либо офлайн-перемером по
сохранённым отчётам. `plan.md` и `tasks.md` не пишутся.

**Owner surface**:
`core/config.py` — `load_system_prompt` (`:~1290-1352`: формат шаблона без слота под контекст
документа; аргумент `source_text` уходит только в `build_translation_domain_instructions`);
`text/translation_domains.py` — `build_terminology_plan` (сканирует `source_text` только для
домена `theology`); `pipeline/support.py` — `resolve_system_prompt`; `pipeline/block_execution.py`
— `_build_prompt_source_text` (`:726-740`), `_get_cached_system_prompt` (`:885-910`), диспозиции
блока (`:1200-1260`), `CONTROLLED_BLOCK_FAILURE_POLICY` (`:42-60`);
`resources/prompts/system_prompt.txt`; `pipeline/quality_gate.py` —
`_collect_untranslated_body_samples` (`:498-532`), эскалация (`:1716-1745`),
`_resolve_list_fragment_regression_gate_samples` (`:231-279`), решение по остатку (`:1641-1680`);
`pipeline/quality_gate_text_detectors.py` — `_is_citation_form_list_fragment_sample` (`:110-135`);
`pipeline/output_validation.py` — `classify_processed_block` (`:366-392`),
`collect_list_fragment_regression_samples` (`:2475-2500`); `validation/acceptance.py` — проверки
`list_fragment_regressions_present`, `untranslated_prose_not_delivered`, `key_headings_preserved`;
`pdf_import/logical_import.py` — `_can_continue_heading_with_line`, `_reconcile_display_titles`;
`text/glossary_pass.py`, `pipeline/glossary_phase.py`, `resources/prompts/glossary_*.txt`.

**Companion**: `specs/063-translation-fidelity/spec.md` — прогон, который всё это показал, записан
в её Changelog за 2026-11-07; её SC-001, SC-005, SC-006 остаются незакрытыми до правок отсюда.
`specs/062-image-models-refresh/spec.md` — FR-033 объясняет ноль вызовов анализа картинок в
прогоне (не дефект, см. R-8). `specs/061-source-ships-under-green/spec.md` — поле
`paragraph_status` на записи сборки, которым пользуются R-2 и R-3.

## Что измерено

Прогон `20261107T_fidelity2_translate_<slug>` на `aca048a`, профиль
`ui-parity-translate-benchmark-advisory-image-safe-no-cleanup`, модель
`openrouter:google/gemini-3.1-flash-lite-preview`, по одной книге, базовая линия — прогон
2026-11-07 на `f4d5562`. Сводка — `artifacts/translate_four_book_run_2026-11-07_after/README.md`,
полная таблица «до → после» — `D:\Temp\docxai-runs\2026-11-07-translate-after\COMPARISON.md`
(вне git, с `comparison.json` и скриптами).

| | Money | CW | RM | VoE |
|---|---:|---:|---:|---:|
| результат | failed (**blocked**) | succeeded | succeeded | succeeded |
| проваленные проверки | `pipeline_succeeded`, `translation_quality_report_not_failed` | `list_fragment_regressions_present`, `key_headings_preserved` | `list_fragment_regressions_present`, `untranslated_prose_not_delivered` | `list_fragment_regressions_present` |
| числовые токены, созданные/удалённые сборкой | 0/0 (было 5/0) | 0/0 (10/0) | 0/0 (56/16) | 0/0 (52/1) |
| маркеры сносок сохранены | 100 % (96,3) | 100 % (96,7) | 100 % (89,7) | 100 % (89,7) |
| абзацев `policy_kept_source` | 25 | 0 | 120 | 307 |
| controlled-fallback блоков | 1 | 0 | 1 | **209** (было 49) |
| следование своему глоссарию, % | 66,1 (было 69,1) | 73,6 (75,4) | 60,2 (61,2) | 62,7 (68,1) |
| prompt-токенов на текстовый вызов | +5 % | | | |

Что спека 063 починила, подтверждено: инвариант чисел (P0) держится на всех четырёх; маркеры
сносок 100 %; разорванные заголовки целы; блокер VoE 592 не воспроизводится; страница копирайта RM
переведена. Это не предмет этой спеки.

## Verified findings

Каждая находка проверена оркестратором по коду на `3bfadd6`; номера строк — оттуда.

- **R-1 (P0, системный, старше 063). Контекст документа никогда не попадает в промпт.**
  `block_execution._build_prompt_source_text` (`:726-740`) склеивает доменные инструкции и
  `document_context_prompt` (план документа, стилевые указания, доменный глоссарий из
  `processing/preparation.py:560`, а с 063 — и глоссарий прогона) и передаёт результат в
  `resolve_system_prompt` как `source_text`. `core/config.load_system_prompt` подставляет в
  `system_prompt.txt` шесть слотов (`source_language`, `target_language`, `operation_instructions`,
  `editorial_intensity_instructions`, `translation_domain_instructions`, `example_block`), слота под
  контекст нет, а `source_text` уходит только в `build_translation_domain_instructions` →
  `build_terminology_plan`, которая для любого домена, кроме `theology`, возвращает `""`
  (`text/translation_domains.py`). Текст контекста модель не видит ни в одном вызове. Тесты
  `tests/test_document_pipeline.py:3358-3401` и `:8737-8770`
  («…every_block_prompt_carries_it») проверяют захваченный kwarg `source_text` ЗАГЛУШКИ
  `load_system_prompt`, а не собранный промпт, — вакуумны. Измерено: следование глоссарию не
  выросло ни на одной книге (таблица выше), prompt-токены на вызов +5 % при секции в ~4 000
  символов. Следствие: всё, что когда-либо клалось в `document_context_prompt`, включая режим
  главы в UI, не влияло ни на один прогон.
- **R-2 (P0, создан 063). Шлюз качества считает `policy_kept_source` непереведённым телом и
  блокирует книгу.** `_collect_untranslated_body_samples` (`quality_gate.py:498-532`) пропускает
  заголовки, подписи и `controlled_fallback`, но не статус абзаца; эскалация
  `untranslated_body_text_above_threshold` (`:1716-1745`, фатальна по `:185-187`) сработала на Money:
  19 027 символов, 3,5 % при порогах 2 000 / 2 %, все четыре образца — абзацы `references` с
  `back_matter_section=references`. В UI книга не доставлена. На трёх других книгах доля ниже порога
  (`review_required`), то есть блок — пересечение порога, а не свойство книги: любая книга с большим
  списком литературы его пересечёт.
- **R-3 (P1, вскрыт P0 спеки 063). Приёмка `list_fragment_regressions_present` падает на
  библиографических строках, оканчивающихся годом.** Гейтовые образцы CW 11 / RM 2 / VoE 42 (сырые
  53 / 117 / 149) — строки вида «Meadows, … Chelsea Green, 2004.», «Press, 1989), p. 135 and Meek,
  *The Economics of Physiocracy*, p. 158.», «(London: Macmillan, 1936), гл. 24.»:
  `_DANGLING_NUMBER_PATTERN` (`output_validation.py:116`, `\d+\.$`) ловит год в конце,
  `_is_citation_form_list_fragment_sample` (`quality_gate_text_detectors.py:110-135`) даёт им один
  сигнал из двух нужных (нет «…», нет второго маркера), и один некредитованный образец переводит
  весь остаток в hard-fail (`quality_gate.py:535-556`). До 063 перенос «2004.» на следующую строку
  прятал хвост — проверка проходила на одной ошибке поверх другой. Формально запись сборки
  (`FinalAssemblyEntry.paragraph_status`) и соседние записи знают, что строка — удержанный по
  политике аппарат или элемент списка литературы, но гейт этим не пользуется.
- **R-4 (P1, создан 063). Эхо цитатных примечаний считается controlled fallback.** VoE: 209 блоков
  / 312 пар / 24 990 символов в `notes`, 302 из 312 — блоки, которые модель вернула без изменений
  (цитатные примечания и URL: «3. https://www.ft.com/…», «Goldman Sachs Annual Report, 2016.»).
  Правило 12 промпта велит цитаты оставлять, модель так и делает, а `classify_processed_block`
  (`output_validation.py:366-392`) по правилу пары 059 классифицирует неизменённый вывод как
  `source_text_fallback` → `fallback_continue` (`block_execution.py:45`) → счётчик fallback, артефакт
  в `block_fallbacks/`, предупреждение в UI. Итог по региону: notes доставлены 413 как исходник /
  274 переведены — две политики в одной секции, SC-005 спеки 063 для notes не выполнен. RM: notes
  47/218, index 36/395; CW: notes 143/99 (секции `references` у CW нет).
- **R-5 (P2, создан 063). Подпись к рисунку типизирована заголовком на импорте.** CW p0445 «peak
  experience endurance-sus tainability» (разорванное слово — текст из диаграммы) получил
  `heading_level=3`, модель слила его с телом → `key_headings_preserved` падает
  (`demoted_heading_count=1`, `content_survived_but_heading_demoted`). Одна строка на четырёх книгах.
- **R-6 (P2). `untranslated_prose_not_delivered` падает на двух символах.** RM:
  `untranslated_prose_block_delivery_count=1`, `chars=2`, `source_text_fallback`. Проверка без
  нижней границы считает двухсимвольный остаток непереведённой прозой.
- **R-7 (P2, наблюдение). По одной паре `omitted` на CW (1749, примечание про Кнаппа и хартализм,
  300+ символов) и VoE (1914, примечание про Умунну) доставлено исходником.** Канал 061 работает как
  задуман (абзац не потерян), но это единственные абзацы прозы на английском в телах книг.
- **R-8 (не дефект). Ноль вызовов анализа картинок на всех четырёх книгах** (было 43/62/55/42):
  спека 062 FR-033 — в режиме `safe` план PIL-only и vision-вызов не оплачивается
  (`image/pipeline.py:1243-1250`, `enable_vision=False`). Экономия в таблице стоимости — в основном
  это, а не политика аппарата. Записывается в Changelog 062, правок не требует.
- **R-9 (P1, создан 063). Сам глоссарий содержит неверные записи**, хотя из-за R-1 модель его не
  видела: Money `sustainability -> жизнеспособность` (развод коллизии переименовал частый термин, а
  не редкий — sustainability «устойчив-» в 129 из 144 пар), RM `Resilience -> живучесть` (0 из 18
  пар), `Lietaer -> Литар` (Money) / `Лита` (RM) при `Bernard Lietaer -> Бернар Лиетар` (CW) —
  фамилия не наследует передачу полного имени; VoE без записи `value`; служебные записи (`growth`,
  `after`, `itself`, `banking -> банковское дело`) занимают бюджет 4 000 символов; Money оставил
  `US`/`USA -> США`, RM `WIR`/`Wired`/`Wörgl` коллизиями. Числа — `glossary.json` четырёх прогонов
  в `D:\Temp\docxai-runs\2026-11-07-translate-after\<slug>\`.

## User Scenarios & Testing *(mandatory)*

### US-1 — Контекст прогона доходит до модели (P0)

Переводчик включает глоссарий прогона или режим главы с планом документа и ожидает, что модель
получит эти указания в каждом вызове.

**Independent Test**: тест собирает РЕАЛЬНЫЙ системный промпт через `load_system_prompt` (не
заглушку) и проверяет, что в тексте, переданном провайдеру, есть секция контекста; второй тест —
что без контекста секции нет и промпт байт-в-байт прежний.

### US-2 — Книга с большим списком литературы доставляется (P0)

Переводчик получает Money & Sustainability целиком, а удержанные по политике списки литературы
видит в сводке как удержанные, не как непереведённую прозу.

**Independent Test**: офлайн-перемер шлюза по сохранённому отчёту Money даёт
`untranslated_body_text_review_required`/ничего вместо блокировки; детерминированный тест с
записями `policy_kept_source` на английском.

### US-3 — Приёмка не падает на библиографии и эхо примечаний не считается потерей (P1)

**Independent Test**: офлайн-перемер приёмки по четырём отчётам: `list_fragment_regressions_present`
проходит на CW/RM/VoE; контрпримеры со сломанными маркированными списками тела по-прежнему падают;
на VoE controlled-fallback блоков ≤ 10 при той же доставке.

## Requirements *(mandatory)*

- **FR-001 (R-1)**: `load_system_prompt` получает отдельный аргумент контекста документа и слот в
  `system_prompt.txt` (своя секция после домена и терминологии); `resolve_system_prompt` и
  `_get_cached_system_prompt` передают туда `document_context_prompt`; `source_text` остаётся
  тем, чем был (вход сканера терминов). Без контекста промпт не меняется ни на байт.
- **FR-002 (R-1)**: тесты `:3358-3401` и `:8737-8770` переписываются на проверку СОБРАННОГО
  промпта, который получил клиент (`client.calls[*]` → системное сообщение), а не kwarg заглушки;
  добавляется гард, что `load_system_prompt` использует аргумент контекста (тест с реальным
  загрузчиком).
- **FR-003 (R-1)**: стоимость — секция контекста входит в кэшируемый системный промпт один раз на
  прогон; событие `run_glossary_built` или сводка прогона печатает длину системного промпта в
  символах, чтобы следующий прогон мог подтвердить доставку по prompt-токенам.
- **FR-004 (R-2)**: `_collect_untranslated_body_samples` и `_collect_untranslated_structural_samples`
  пропускают записи с `paragraph_status == policy_kept_source`; комментарий у эскалации называет это
  третьим исключением рядом с `controlled_fallback`. Доля считается от того же знаменателя.
- **FR-005 (R-3)**: остаток `list_fragment` кредитуется по РЕГИОНУ и СТАТУСУ записи сборки, не
  только по форме: образец, разрешённый в запись `policy_kept_source` или в запись списка
  литературы/примечаний (по `list_kind`/роли соседей), уходит в review, не в hard-fail. Форменное
  кредитование можно расширить сигналом «автор-форма в начале строки» только с замером ложных
  срабатываний на четырёх `delivered.md`. Контрпримеры тела (сломанные маркеры, строчная буква после
  тире) обязаны по-прежнему падать — существующие counter-proof тесты не трогаются.
- **FR-006 (R-4)**: неизменённый вывод модели для абзаца блока с `back_matter_section ∈ {notes,
  references}` при операции `translate` записывается диспозицией `policy_kept_source` (удержан под
  правилом 12), не `source_text_fallback`: без артефакта в `block_fallbacks/`, без счётчика
  fallback, с учётом в `back_matter_*` семействах. Блок с хотя бы одним переведённым абзацем —
  обычный блок; абзац прозы, эхо которого в notes не цитата по форме (≥ N слов без сигналов
  цитаты), остаётся `source_text_fallback` — N и число таких абзацев на VoE (ожидается ≈ 10 из 312)
  измеряются и записываются в Changelog.
- **FR-007 (R-5)**: правило заголовка на импорте не повышает строку с разорванным внутри слова
  переносом или без завершённого слова; если без потерь на 45/45 названий глав (замер 063) это не
  делается, R-5 записывается в Non-goals с числом.
- **FR-008 (R-6)**: `untranslated_prose_not_delivered` считает только остаток с видимыми символами
  не меньше минимума якоря (константа из 059/061, не новая), либо двухсимвольный блок перестаёт
  быть fallback — по тому, что покажет сам блок RM.
- **FR-009 (R-9)**: развод коллизии сохраняет передачу термину с бо́льшим числом вхождений и просит
  модель переименовать редкий (частоты передаются в вызов C); запись фамилии наследует передачу
  записи полного имени того же семейства (правило формы, не словарь); обязательный кандидат «marked
  ∧ recurring» требует многословности, заглавной буквы или определения — одиночное строчное слово
  под выделением становится необязательным кандидатом с рангом по частоте. Каждое правило
  замеряется на четырёх `glossary.json` и дампах кандидатов (`scripts/measure-glossary-candidates.py`)
  до и после; числа — в Changelog.
- **FR-010**: после правок — третий платный прогон тех же четырёх книг тем же профилем; отчёт
  «до → после» тем же скриптом; затем повторное ревью Money и VoE по методике 063 SC-007.

## Success Criteria *(mandatory)*

- **SC-001**: Тест с реальным `load_system_prompt` видит секцию контекста в системном сообщении
  клиента; вакуумных проверок по kwarg заглушки не остаётся (`grep prompt_sources`).
- **SC-002**: Офлайн-перемер шлюза по отчёту Money: не `blocked`; на трёх других — статус не хуже.
- **SC-003**: Офлайн-перемер приёмки: `list_fragment_regressions_present` проходит на CW, RM, VoE;
  counter-proof тесты тела остаются красными на своих входах.
- **SC-004**: На отчёте VoE controlled-fallback блоков ≤ 10 (было 209) при доставке, равной
  байт-в-байт; `block_fallbacks/` без цитатных эхо.
- **SC-005**: Полный прогон `scripts/test.sh tests/ -q` зелёный в главном дереве; pyright без новых
  ошибок.
- **SC-006** *(после FR-010)*: Money доставлена; следование своему глоссарию ≥ 85 % на каждой книге
  на терминах с ≥ 3 парами; 063 SC-006 (≤ 1 передача у ≥ 90 % ключевых терминов) замерен честно,
  каков бы ни был.

## Порядок исполнения

Четыре агента, непересекающиеся файлы, один worktree на агента вне репозитория:

1. **gate** — FR-004, FR-005, FR-008: `pipeline/quality_gate.py`, `quality_gate_text_detectors.py`,
   `validation/acceptance.py`, их тесты, офлайн-перемер по четырём отчётам.
2. **prompt** — FR-001…FR-003: `core/config.py` (`load_system_prompt`), `pipeline/support.py`,
   `resources/prompts/system_prompt.txt`, `block_execution.py` ТОЛЬКО `:726-740` и `:885-910`,
   `tests/test_document_pipeline.py` (два теста), `tests/test_config.py`.
3. **notes** — FR-006, R-7: `block_execution.py` диспозиции (`:1200-1260`) и политика отказов,
   `output_validation.py` классификатор (без функций переноса номера), `block_failures.py`,
   `test_spec_063_apparatus_policy.py`, `test_spec_059_*`.
4. **import-glossary** — FR-007, FR-009: `pdf_import/logical_import.py`, `text/glossary_pass.py`,
   `pipeline/glossary_phase.py`, `resources/prompts/glossary_*.txt`, их тесты,
   `scripts/measure-glossary-candidates.py`.

Оркестратор: слияние, полный прогон, приёмочное ревью Codex по всем затронутым поверхностям,
FR-010, статусы спек 062/063/064 и `docs/WHERE_WE_ARE.md`.

## Non-goals

- Не менять правило 12 промпта и решение D1 спеки 063 (аппарат по региону): R-4 — ошибка учёта,
  а не политики.
- Не включать vision-вызов в режиме `safe` (R-8 — по дизайну 062 FR-033).
- Не трогать `decide_list_fragment_carry` и инвариант чисел P0 спеки 063: R-3 решается на стороне
  гейта, а не возвратом переноса, который прятал хвосты.
- Не ослаблять порог 2 000 / 2 % эскалации (R-2 решается исключением статуса, не порогом).
- Не вводить списков слов для глоссария (стоп-слова, «служебные» термины): R-9 решается формой
  (многословность, регистр, определение, частота) — Конституция VII.
- Не повторять ревью Money/VoE до третьего прогона (FR-010): до R-1 измерять эффект глоссария
  бессмысленно.
- Не ранжировать необязательное однословное выделенное слово «частота × число выделений» ВНУТРИ
  квоты семейства (FR-009, правило 3): замерено 2026-11-07 на четырёх книгах — как балл такое
  слово вытесняло из квоты обязательные многословные выражения (VoE *unearned income*, CW
  *technological capital*), как отдельный последний ярус — выталкивало из кандидатов вовсе
  (Money *efficiency*) и поднимало обязательных 93 → 109 за счёт названий изданий (*American
  Economic Review*, *York Times*). Оставлен прежний балл (частота × idf × разброс); правило 3
  меняет только обязательность.

## Anti-regression

1. Тесты счётчика чисел и реплея 063 (`DOCXAI_TRANSLATE_REPLAY_ROOT`) не трогаются и остаются
   зелёными.
2. Эскалация `untranslated_body_text_above_threshold` по-прежнему срабатывает на английской прозе
   тела без статуса (существующий тест) — исключение только по `policy_kept_source`.
3. Counter-proof тесты `list_fragment` на сломанных списках тела остаются красными на своих входах.
4. Правило пары 059 (`delivered_text_equals_source` — единственное место сравнения) не дублируется:
   FR-006 меняет ДИСПОЗИЦИЮ по региону, а не предикат.
5. Без `document_context_prompt` системный промпт байт-в-байт прежний (снимок в тесте).
6. Полный прогон в главном дереве после слияния всех четырёх веток; `git status --porcelain` пуст
   перед «зелёным».

## Assumptions

- Отчёты прогона в `D:\Temp\docxai-runs\2026-11-07-translate-after\` (вне git) доступны агентам по
  абсолютному пути; офлайн-перемер — через `build_report_acceptance_verdict` и шлюз по сохранённому
  `final_markdown`/реестру, без вызовов модели.
- Третий платный прогон (FR-010) стоит ≈ $2,4 и идёт после приёмочного ревью.

## Changelog

- 2026-11-07 — спека создана по отчёту повторного прогона (`3bfadd6`); R-1 найден оркестратором
  при проверке утверждения прогона «глоссарий не повлиял» — трассировкой
  `document_context_prompt` до `load_system_prompt`.

- 2026-11-07 (import-glossary) — **FR-007 и FR-009 сделаны** (ветка `064/glossary`). Замеры —
  офлайн по `source_paragraphs.json`/`glossary.json` прогона `2026-11-07-translate-after` (кандидаты
  из них воспроизводят кандидатов прогона один в один на всех четырёх книгах) и повтором импорта
  четырёх PDF (`build_paragraph_units_from_text_spans`), без вызовов модели.
  **FR-007 (R-5).** Форма, которую даёт PDF: ячейки схемы стоят на одной базовой линии с другой
  короткой строкой того же кегля через горизонтальный зазор (CW стр. 49: «Peak Experience» |
  «Endurance-Sus tainability», 5,76 pt при теле 14,4). Такая строка (и ещё одна в пределах строки от
  неё того же кегля — ячейка заголовка таблицы, две ячейки, слитые экстрактором в одну строку) не
  повышается типографским путём заголовка, если не набрана крупнее тела
  (`pdf_import/logical_import.py` `_detect_table_row_span_keys`, `_is_table_row_cell`;
  проверка в `_looks_like_pdf_heading_candidate`); граница «короче половины строки тела» держит
  двухколонный набор вне правила. Заголовков: Money 174 → 170, CW 255 → 244, RM 185 → 159, VoE
  132 → 132; все снятые — ячейки схем (CW стр. 49, 132–133; RM стр. 151), подписи предисловия
  Money, строки указателя RM; заголовки уровней 1–2 совпадают на всех четырёх книгах — 45/45
  названий глав целы. p0445 больше не заголовок; остаток той же схемы — один заголовок RM «Bank».
  Сигнал «разрыв внутри слова» проверен и не взят: в Money/CW настоящие пробелы — глифы, разрывы
  выведены pdfminer, но тот же сигнал (и кегль 0,4 тела) несут и заголовки врезок Money («Box 6.1
  – Chronicle of a Pre dictable De bt Cris is»), которые 063 считает настоящими. Уточнение к R-5:
  строка была заголовком h3 и до 063 (прогон `2026-11-07-translate`, p0449) — дефект старше 063.
  **FR-009.** (1) Коллизия: группа упорядочена по числу вхождений, первый член и его написания
  сохраняют передачу, вызов C получает `count` и `keep`, а код применяет ответ только к остальным,
  что бы модель ни вернула (`text/glossary_pass.py` `order_collision_group`, `collision_keepers`;
  `pipeline/glossary_phase.py` `_apply_distinction`). Не коллизия по форме: два написания одного
  имени (равны без регистра, точек и строчной `s` множественного; аббревиатура и та же плюс одна
  буква — US/USA; `same_spelling_family`) и два имени, оставленные как написаны (правило основ
  резало «Wired» до «wir»; `_collision_rendering_key`). По группам прогона до C: Money 4 → 3
  (US/USA снята), сохраняют передачу sustainability (114) перед resilience (33), window of
  viability (4) перед vitality (1), structure (31) перед framework (26); RM 3 → 2 (WIR/Wired
  снята), Wörgl (22) сохраняет «Вёргль» (вызов C прогона переименовал именно его в «вергль»),
  monetary system (33) перед money system (29); VoE — surplus value (36). Неразведённых в итоговых
  глоссариях по новому правилу: Money 1 → 0, RM 2 → 1 (simply the Wörgl). (2) Имена: короткая
  форма, слова которой заканчивают более длинное имя, а добавленные слова тело никогда не пишет
  строчными («Central Vermont», «Great Depression», «New England» — другие сущности), — член
  семьи; неоднозначная (кончает два разных имени) и обязательная остаются кандидатами; форма,
  ни разу не стоящая отдельно (все вхождения внутри полного имени), отбрасывается
  (`_name_family_heads`, `split_name_families`). Член в модель не уходит, голова несёт счёт его
  отдельных употреблений, после вызовов член наследует конец передачи головы, если она
  пословная и не оставлена латиницей (`inherit_name_renderings`). Членов: Money 8 (Lietaer ←
  Bernard Lietaer, Daly, Friedman, Georgescu-Roegen, Diamond, Ulanowicz, Kippu, America ← Latin
  America), CW 3 (Cahn, Newburgh ← Plan-It Newburgh, Columbia ← British Columbia), RM 10 (Lietaer,
  Dunne, Lub, Cahn, Fisher, Adams, DeMeulenaere, Van Arkel, Linton, Kampers), VoE 5 (Marx, Keynes,
  Ricardo, Marshall, Stiglitz). Риск: если модель не выберет голову (имена необязательны; Money
  «Bernard Lietaer» в прогоне не выбран), у члена записи не будет — голова теперь показывает
  модели счёт семьи (Money 32, VoE Marx 95). RM «Bernard Lietaer» стал обязательным (см. (4)).
  (3) «Отмечено ∧ повторяется» требует ещё многословности, заглавной буквы (по счёту самого тела:
  с заглавной в середине фразы чаще, чем строчными) или определения; одиночное строчное
  выделенное слово — необязательный кандидат (`_is_lowercase_single_marked`). Обязательных
  93/80/110/89 → **83/74/96/87**; одиночных строчных среди них 42/31/56/24 → 32/27/51/25. До правки
  одиночные строчные обязательные шли маршрутами: выделение без определения 10/10/7/5 (Money after,
  solution, credit, structural, taxes, resilience, annual, fail, pure, explicitly; CW economy,
  feedback, money, potential, green, stock, increasing, intentional, multiplier, velocity; RM amount,
  really, reducing, compound, talents, structural, isolation; VoE surplus, risks, makers, month,
  takers), определение 9/13/14/13, h1 23/3/31/4, голова 0/5/4/2. Правило 3 снимает первый маршрут
  (solution и really остаются через h1). Остаток одиночных строчных — слова h1 (RM from, into,
  than, what, about, within, three, isn’t), головы и определения-идиомы (home, careers, loser) —
  вне правила 3. (4) Соседние выделенные прогоны «`*a* *b*`» — одно выражение (импорт закрывает
  курсив на каждом слове): growth hierarchy, shareholder primacy, Pareto distribution, Bernard
  Lietaer, Jacqui Dunne, potential exchange capital; потеряны *technological capital* («*built
  and* *technological capital*») и *local currencies* («*community* *or local currencies*»).
  Определение «call X ‘Y’» называет помеченное Y, а не дополнение X, если Y завершает фразу:
  itself → Post-Autistic Economics, british → consols, landlords → unproductive, consumer →
  preferences. С каждым правилом выключенным по очереди обязательных: без правила 3 —
  93/81/106/94, без склейки — 82/73/99/86, без правила дополнения — 83/73/96/87. (5) **VoE
  `value`** был кандидатом семейства heading (слово h2, 894 вхождения в теле) и необязательным:
  заглавие книги в h1 импортировано вразрядку («T H E VA L U E O F E V E RY T H I NG»), главы VoE —
  h2, курсив *value* (p0091) не первое употребление в своей десятой части, кавычки вокруг одного
  слова правило не считает; вызов B его не выбрал. Как голова семьи (value added — обязательный —
  surplus value, theory of value…) он пропускался, потому что уже был кандидатом другого
  семейства. Правка формы: слово, найденное другим путём, тоже голова, если в семье есть
  обязательный член (`extract_glossary_candidates`, ветка головы). Обязательными так стали VoE
  value, public, economy, economics, wealth; CW cities, economics, human, social. (6) Бюджет 4 000
  символов: обязательный раздел по передачам прогона (неизвестные — по средней длине записи)
  ≈ 2 907 / 2 883 / 2 965 / **3 781**, места для необязательных ≈ 35 / 32 / 34 / **6** записей.
  Рекомендация, не правка: на VoE обязательные съедают почти весь бюджет и имена (Marx, Keynes)
  будут срезаться; поднять `glossary_prompt_max_chars` до ~5 000 (≈ +250 токенов на вызов) —
  решать после того, как R-1 доставит раздел и FR-010 покажет следование. Тесты —
  `tests/test_pdf_text_layer_logical_import.py` (`test_fr007_*`), `tests/test_glossary_pass.py`
  (`test_fr009_*`); два прежних теста 063 переписаны под правило 3 (*brennic* одним строчным
  словом теперь необязателен, «marked twice» — на двухсловном *brennic rule*).
