# Codex Review — spec 073 before the plan (2026-11-10)

- **Date:** 2026-11-10
- **Reviewed:** `specs/073-narration-for-the-ear/spec.md` on `main` @ `8b88908` (draft), before any plan or code
- **Reviewer:** Codex `gpt-6-astra`, `codex exec --sandbox read-only`; 191 080 tokens
- **Scope:** every claim of «Что есть сейчас» checked against the code; feasibility of each requirement; the ElevenLabs and MiniMax probe data, the spec 072 implementation in `072/integration`
- **Status:** verdict «СТРОИТЬ ПОСЛЕ ПРАВОК»; 3 P1 + 7 P2 + 1 P3 — all verified by the orchestrator and landed in the spec (Changelog 2026-11-10)
- **Canonical source of truth:** `specs/073-narration-for-the-ear/spec.md` and the code; this report is not (see `docs/reviews/README.md`)

## Поднято / вердикт / приземление

| # | Находка | Вердикт оркестратора | Приземление |
|---|---|---|---|
| 1 (P1) | Нет контракта сигнала разделителя сцены; склейка через разделитель | ПОДТВЕРЖДЕНО | FR-006 |
| 2 (P1) | «Абзацы через перевод строки» против равенства с .tts.txt; пауза внутри серии | ПОДТВЕРЖДЕНО | FR-007 |
| 3 (P1) | Механизм 063 — до пяти вызовов; 842 кандидата; бюджет | ПОДТВЕРЖДЕНО | FR-004: один вызов, только сокращения, предел N; имена — Non-goal |
| 4 (P2) | Номера разделов не представимы записью глоссария | ПОДТВЕРЖДЕНО | FR-005 — правило промпта |
| 5 (P2) | Доставка словаря в основной и исправляющий промпты не определена | ПОДТВЕРЖДЕНО | FR-004: поблочно по исходнику, оба промпта; SC-007 |
| 6 (P2) | Конфликт правил аббревиатур и инициалов; единица счёта latin | ПОДТВЕРЖДЕНО | FR-003 |
| 7 (P2) | Протечка контекста режет по U+0301; точная сборка не должна нормализоваться | ПОДТВЕРЖДЕНО | FR-002 |
| 8 (P2) | Ударение в PDF без критерия | ПОДТВЕРЖДЕНО | FR-009, Non-goal |
| 9 (P2) | SC-002…004 вакуумны, смешивают причины | ПОДТВЕРЖДЕНО | SC-002…SC-005 переписаны |
| 10 (P2) | Раннер не получает .minimax.txt | ПОДТВЕРЖДЕНО | FR-008 |
| 11 (P3) | «Глава четыре» неверно; TRC/CoR-EU не из файла главы | ПОДТВЕРЖДЕНО | «Что измерено» исправлено |

## Промпт

```text
Ты работаешь в том же окружении, что и оператор: читай любые файлы по абсолютным путям, включая исключённые из git, считай сам — Python и git у тебя есть. WSL тебе закрыт, поэтому наши тесты и пайплайн ты не запустишь. НЕ ВЫДУМЫВАЙ измерений; число, которого нет в файлах, называй прогнозом и говори, чем его проверить. Ничего не меняй в файлах.

Задача: проверка корректности и полноты СПЕКИ до плана и до кода. Репозиторий D:\Work\Projects\DocxAICorrector, ветка main (выполни git -C D:\Work\Projects\DocxAICorrector log --oneline -3). Спека: D:\Work\Projects\DocxAICorrector\specs\073-narration-for-the-ear\spec.md (+ checklists\requirements.md). Правила: AGENTS.md, .specify\memory\constitution.md (III, VII — правила по форме без словарей и литералов книг, в тестах тоже; VIII; Spec Format Contract).

Суть: режим аудиокниги (спека 070, D:\Work\Projects\DocxAICorrector\specs\070-audiobook-technical-pass\spec.md) готовит переведённый текст к озвучке. Спека 073 добавляет: ударения знаком U+0301 в омографах (правило промпта), транслитерацию латиницы (правило промпта + новый класс остатка `latin`, исправляется тем же единственным вызовом на блок), словарь чтения книги (один вызов модели на книгу на механизме глоссария перевода спеки 063), версию `.minimax.txt` с паузами `<#x#>` по структуре. Строится ПОСЛЕ спеки 072 (D:\Work\Projects\DocxAICorrector\specs\072-narration-docx-pdf\spec.md; её реализация идёт в ветке 072/integration, рабочее дерево D:\Temp\claude\wt-072 — там уже есть группы абзацев с уровнем заголовка `NarrationGroup`, план документа `pipeline\narration_document.py`, DOCX/PDF, группа результата, экран; читай и это дерево, когда спека 073 на них опирается).

Данные проб (вне git): D:\Temp\docxai-research\minimax-tts\RESEARCH.md (разделы «Проба разметки через API», «На слух»), probe.py, probe_out\ (transcripts.json, probe_log.json); D:\Temp\docxai-research\elevenlabs-studio\RESEARCH.md (раздел «Проба владельца»), el_probe_C.transcript.json; вывод замера 070: D:\Temp\docxai-research\070-fr009\pairs\money_ch3_pairs_all.md, runs\archive\.

Поверхности (пути от D:\Work\Projects\DocxAICorrector\src\docxaicorrector\): resources\prompts\operation_audiobook.txt, system_prompt_audiobook.txt, operation_audiobook_repair.txt; text\narration_residue.py, narration_coverage.py, narration_cleanup.py; document\narration_exclusion.py (_without_combining_marks, правило обрывка); pipeline\narration_postprocess.py (склейка, границы); pipeline\audiobook_pass.py, audiobook_repair.py, block_execution.py (финализация, исправление); pipeline\glossary_phase.py, text\glossary_pass.py, pipeline\_pipeline.py (глоссарий перевода: кандидаты, бюджет, секция, вызов, учёт стоимости, артефакт); core\model_accounting.py (стадии); runtime\artifacts.py, runtime\artifact_retention.py; ui\_ui.py.

Что проверить:
1. Верны ли ссылки «Что есть сейчас» (file:line) и утверждения про пробы (сверь с файлами проб).
2. FR-001/FR-002: ударения — где ещё знак U+0301 сломает проверки (покрытие, остаток ALL_CAPS/ROMAN, обрывок, склейка, разбор границ, кэш, сравнение с исходником, PDF текстовый слой); реалистичность «одного общего помощника».
3. FR-003: класс `latin` — как определить латиницу по форме (имя символа Unicode), исключения (адреса, римские цифры уже свой класс, химические формулы, единицы?), не ломает ли единственность вызова исправления; конфликт с правилом 5 промпта («аббревиатуры оставляйте как есть») и с правилом инициалов.
4. FR-004: реально ли переиспользовать механизм глоссария 063 для словаря чтения (что там специфично для перевода: языки, промпты, правила отбора, кэш, артефакты, гейтинг `glossary_pass_applies`); как отбирать кандидатов по форме на РУССКОМ тексте (имена с заглавной в середине предложения — сколько их на полной Money, прогноз); бюджет; цена; что делать с номерами разделов в заголовках; где граница с Конституцией VII.
5. FR-005: паузы — где взять «разделитель сцены», если исключённые абзацы в сборку не попадают; правило «двух меток подряд нет»; соответствие групп спеки 072 (глава / не глава); равенство с .tts.txt без меток.
6. FR-006/FR-007: связь с контрактами спеки 072 (группа, состояние, экран) — не дублирует ли, не противоречит ли.
7. SC: измеримы ли, не вакуумны ли; что проверяется без платного прогона.
8. Non-goals / Anti-regression: чего не хватает; уровень работы (полный цикл) — оправдан ли; не стоит ли разделить спеку.

Требования к ответу: на каждую находку — file:line (находка без пути не считается); серьёзность P1 / P2 / P3; уверенность. Возражение с конкретной ссылкой ценнее согласия. Ответ по-русски. Последней строкой — вердикт ровно одним из: СТРОИТЬ / СТРОИТЬ ПОСЛЕ ПРАВОК / НЕ СТРОИТЬ.
```

## Ответ Codex (финальный отчёт)

Проверены `main` и рабочее дерево 072. Запрошенный `git log --oneline -3` дал

```text
8b88908 spec 073: stress marks, transliteration, a reading glossary and a MiniMax version for narration (draft)
f6de2fd spec 072: rewritten after the Codex spec review (3 P1 + 6 P2 landed)
2e5e8d5 spec 072: narration text as DOCX and PDF next to the .tts.txt (draft)
```

В дереве 072 прочитана реализация на `f23c97f`. Проверка выполнена чтением файлов и вычислениями через Windows Python. Канонические тесты, пайплайн и PDF-конвертация через WSL не выполнялись. Файлы не изменены.

## Находки

### 1. P1 — Для паузы разделителя сцены отсутствует контракт передачи структурного сигнала

**Уверенность высокая.**

FR-005 требует получить разделитель из исключённого абзаца, используя группы 072. Однако `NarrationGroup` содержит только ID озвучиваемых записей, роль, уровень и текст. Исключённые записи отбрасываются раньше. Более того, сборка может уже склеить два body-абзаца через исключённый разделитель. Тогда нужная граница окажется внутри одной группы. [073/spec.md:128](specs/073-narration-for-the-ear/spec.md:128), [audiobook_pass.py:188](src/docxaicorrector/pipeline/audiobook_pass.py:188), [072/narration_postprocess.py:102](D:/Temp/claude/wt-072/src/docxaicorrector/pipeline/narration_postprocess.py:102), [072/narration_postprocess.py:174](D:/Temp/claude/wt-072/src/docxaicorrector/pipeline/narration_postprocess.py:174)

До плана нужно определить, как позиция разделителя сохраняется от исходных абзацев до сборки и влияет ли она на body-склейку. Нужны случаи с несколькими разделителями подряд, разделителем возле заголовка, в начале и конце книги. Также нужно определить, относятся ли к разделителям пустые абзацы и исключения других причин. Сам признак «нет букв и цифр» этого различия не устанавливает. [073/spec.md:130](specs/073-narration-for-the-ear/spec.md:130), [narration_exclusion.py:139](src/docxaicorrector/document/narration_exclusion.py:139)

### 2. P1 — FR-005 одновременно задаёт несовместимые варианты сериализации

**Уверенность высокая.**

FR-005 говорит «абзацы через перевод строки», а SC-005 требует точного равенства с `.tts.txt` после удаления меток. Реальная сборка TXT использует `"\n\n"`. Замена разделителя на `"\n"` нарушит критерий даже на двух обычных абзацах. Нужно прямо закрепить сохранение всех исходных разделителей и правило удаления только вставленных меток. [073/spec.md:128](specs/073-narration-for-the-ear/spec.md:128), [073/spec.md:155](specs/073-narration-for-the-ear/spec.md:155), [072/narration_postprocess.py:185](D:/Temp/claude/wt-072/src/docxaicorrector/pipeline/narration_postprocess.py:185)

Есть второй выбор. Группы TXT сохраняют соседние заголовки раздельно, а план DOCX объединяет серии, например `2 → 1`, добавляя «. ». Если MiniMax брать из плана DOCX, равенство с TXT нарушится. Если ставить паузу после каждой исходной группы, получится пауза внутри составного названия главы. Следует определить границу паузы через ID серии, сохранив текст TXT. Для совпавших оснований паузы нужен приоритет, например между заголовком и разделителем сцены. [072/narration_document.py:125](D:/Temp/claude/wt-072/src/docxaicorrector/pipeline/narration_document.py:125), [072/narration_document.py:176](D:/Temp/claude/wt-072/src/docxaicorrector/pipeline/narration_document.py:176)

Актуальная 072 также переводит подзаголовки в `Normal`. Поэтому определять их для MiniMax по стилю DOCX нельзя. Сохраняется `source_heading_level`, а глава определяется через `chapter_level`. FR-007 следует явно сохранить существующие слияния и преобразования 072. [072/narration_document.py:70](D:/Temp/claude/wt-072/src/docxaicorrector/pipeline/narration_document.py:70), [072/narration_document.py:168](D:/Temp/claude/wt-072/src/docxaicorrector/pipeline/narration_document.py:168), [073/spec.md:136](specs/073-narration-for-the-ear/spec.md:136)

### 3. P1 — «Один вызов на механизме 063» требует уточнения границ переиспользования и бюджета

**Уверенность высокая.**

Текущий механизм глоссария допускает **до пяти вызовов**. Есть обязательная часть, повтор половинами, дополнительный запрос и разрешение коллизий. Прямое переиспользование фазы нарушит FR-004. Переиспользовать отдельные компоненты возможно, но спека должна закрепить самостоятельную политику одного вызова, включая SDK-повторы, Stop, пустой список и частичный ответ. [073/spec.md:121](specs/073-narration-for-the-ear/spec.md:121), [glossary_phase.py:680](src/docxaicorrector/pipeline/glossary_phase.py:680), [audiobook_repair.py:78](src/docxaicorrector/pipeline/audiobook_repair.py:78)

Я пересчитал сохранённые **1 227 исходных озвучиваемых абзацев полной Money**, применив `_plain` и `_capitalised_runs`, исключив серии, помеченные помощником как начальные.

| Отбор по форме | Вхождения | Различные написания |
|---|---:|---:|
| Все полученные серии с заглавными | 1 617 | 842 |
| Серии только с кириллическими буквами | 1 256 | 708 |

Это промежуточный форменный отбор. Здесь есть имена, сокращения, падежные варианты и прочие слова с заглавной. Семейное ранжирование полного переводческого extractor к этим числам не применялось. Источник и правило доступны для повторного подсчёта. [money_book_source.txt:1](D:/Temp/docxai-research/070-fr009/pairs/money_book_source.txt:1), [glossary_pass.py:343](src/docxaicorrector/text/glossary_pass.py:343), [glossary_pass.py:357](src/docxaicorrector/text/glossary_pass.py:357)

Для 842 записей существующая формула запрашиваемого запаса составляет **81 088 токенов**, после чего обрезается потолком **16 384**. Это расчёт бюджета, фактический размер ответа модели неизвестен. Кроме того, 5 900 символов секции сегодня являются расширяемым бюджетом для защищённых записей. Поэтому Assumption «укладываются в бюджет перевода» не ограничивает размер словаря. [glossary_pass.py:1483](src/docxaicorrector/text/glossary_pass.py:1483), [glossary_phase.py:944](src/docxaicorrector/pipeline/glossary_phase.py:944), [073/spec.md:186](specs/073-narration-for-the-ear/spec.md:186)

Нужно определить приоритет кандидатов, предел запроса и политику пропусков. **Прогноз** для широкого отбора на полной Money — сотни записей. Проверить его можно бесплатным извлечением кандидатов на согласованном входе до вызова модели. Оценка `$0,40` должна оставаться прогнозом с учётом новой стадии, добавленных токенов каждого блока и дополнительных исправлений. Сохранённый прежний прогон стоил `$0,340316`. [073/spec.md:141](specs/073-narration-for-the-ear/spec.md:141), [report.json:139](D:/Temp/docxai-research/070-fr009/runs/archive/20261110T074147Z_40074_money_full_standard_translated_ru/audiobook_money_full_standard_translated_report.json:139)

### 4. P2 — Номера заголовков не представимы обычной записью существующего глоссария

**Уверенность высокая.**

Ключ переводческого глоссария состоит из буквенных токенов. Для `"1."` и `"2."` он пустой, и parser отвергает такие записи. Отдельного поля для общей политики нумерации в его ответе нет. При этом FR-004 обещает одновременно чтение каждого кандидата и единую форму номера раздела. [073/spec.md:124](specs/073-narration-for-the-ear/spec.md:124), [glossary_pass.py:337](src/docxaicorrector/text/glossary_pass.py:337), [glossary_pass.py:2128](src/docxaicorrector/text/glossary_pass.py:2128)

Следует отдельно описать политику номеров и её доставку во все соответствующие заголовочные блоки. Она должна опираться на роль и уровень исходника. Формулировка «встречающиеся в блоке записи» недостаточна для общего правила. Для русских имён также нужно определить отношение между словарной формой, падежным вариантом и требованием «читать ровно так». Переводческий промпт сейчас прямо допускает склонение в контексте. [resources/prompts/glossary_required.txt:7](src/docxaicorrector/resources/prompts/glossary_required.txt:7), [073/spec.md:126](specs/073-narration-for-the-ear/spec.md:126)

### 5. P2 — Доставка словаря в основной и исправляющий запросы недоопределена

**Уверенность высокая.**

В текущем audiobook-пути `document_context_prompt` принудительно пуст, загрузчик использует отдельный шаблон, а основной и исправляющий системные промпты кэшируются на весь прогон. Переводческий механизм передаёт общую секцию. Для требуемой поблочной выборки понадобится отдельное добавление секции после получения базового промпта. [support.py:34](src/docxaicorrector/pipeline/support.py:34), [config.py:1802](src/docxaicorrector/core/config.py:1802), [block_execution.py:1234](src/docxaicorrector/pipeline/block_execution.py:1234), [block_execution.py:1500](src/docxaicorrector/pipeline/block_execution.py:1500)

Спека должна явно включить исправляющий запрос в получатели словаря. Иначе исправление латиницы сможет выбрать другое чтение. Отбор для исправления следует связать с исходным блоком, поскольку основной ответ уже мог изменить написание кандидата. Проверка должна сравнивать реальные аргументы двух разных блоков и исправления, включая отсутствие записей предыдущего блока. [073/spec.md:126](specs/073-narration-for-the-ear/spec.md:126), [block_execution.py:1529](src/docxaicorrector/pipeline/block_execution.py:1529)

### 6. P2 — FR-003 оставляет конфликт инструкций и неоднозначный подсчёт `latin`

**Уверенность высокая.**

Основной промпт требует оставлять аббревиатуры как есть. Исправляющий повторяет это требование. Правило инициалов также требует оставить неизвестный инициал. FR-003 предписывает кириллицу для латинских букв, но не устанавливает приоритет новых правил. Особенно важен латинский инициал, который можно передать названием буквы, сохранив запрет на выдумывание полного имени. [operation_audiobook.txt:5](src/docxaicorrector/resources/prompts/operation_audiobook.txt:5), [operation_audiobook.txt:8](src/docxaicorrector/resources/prompts/operation_audiobook.txt:8), [operation_audiobook_repair.txt:1](src/docxaicorrector/resources/prompts/operation_audiobook_repair.txt:1), [073/spec.md:117](specs/073-narration-for-the-ear/spec.md:117)

Нужно зафиксировать единицу счёта и пересечения классов. Например, один ли токен `CoR-EU`, как учитывать смешанную письменность, исключать ли римский токен из `latin`, как маскировать адрес целиком. Для химических формул и единиц вроде `H₂O`, `kg` следует определить ожидаемое словесное чтение либо записать принятую границу. Форменных исключений и словарей химических обозначений спека сейчас не разрешает. [073/spec.md:119](specs/073-narration-for-the-ear/spec.md:119), [073/spec.md:138](specs/073-narration-for-the-ear/spec.md:138), [narration_residue.py:67](src/docxaicorrector/text/narration_residue.py:67)

Добавление класса в существующее множество исправимых остатков совместимо с единственным вызовом. Нужен тест блока, содержащего одновременно несколько классов, с проверкой одной HTTP-попытки. [audiobook_pass.py:204](src/docxaicorrector/pipeline/audiobook_pass.py:204), [audiobook_repair.py:157](src/docxaicorrector/pipeline/audiobook_repair.py:157)

### 7. P2 — FR-002 пропускает сравнение с соседним контекстом и слишком широко требует нормализации границ

**Уверенность высокая.**

Список поверхностей не включает проверку протечки контекста. Она токенизирует через `\w+`, поэтому U+0301 разрывает слова. В изолированном вычислении извлечённых функций на синтетическом восьмисловном предложении протечка обнаруживалась без ударения и переставала обнаруживаться после одного U+0301 внутри слова. Эта проверка вызывается при доставке ответа до narration-финализации. Это Windows-side проверка чистых функций, каноническим тестом она не является. [073/spec.md:113](specs/073-narration-for-the-ear/spec.md:113), [_generation.py:78](src/docxaicorrector/generation/_generation.py:78), [_generation.py:1462](src/docxaicorrector/generation/_generation.py:1462), [_generation.py:1705](src/docxaicorrector/generation/_generation.py:1705)

Общий помощник реалистичен как представление текста для лексического сравнения. Для адресов совпадений потребуется сохранять связь с позициями исходной строки. Проверку точной сборки по ID и текстам следует оставить чувствительной к потере самого ударения. Сейчас она сравнивает записи с собранным текстом напрямую. Корректно поставленный U+0301 также сам по себе не меняет правила начала и конца body-склейки. [narration_postprocess.py:109](src/docxaicorrector/pipeline/narration_postprocess.py:109), [narration_postprocess.py:180](src/docxaicorrector/pipeline/narration_postprocess.py:180)

Подтверждены отдельные уязвимые формы ALL_CAPS и ROMAN. Например, `А́ЛМАЗ ВЕ́ТЕР` теряет необходимое число длинных слов, а `ÍV` перестаёт совпадать с ASCII-римским шаблоном. Правило обрывка уже снимает M*. Для покрытия тест должен содержать минимум четыре длинных слова и шесть токенов. Один «за́мок» находится ниже порогов измерения. [narration_residue.py:122](src/docxaicorrector/text/narration_residue.py:122), [narration_residue.py:142](src/docxaicorrector/text/narration_residue.py:142), [narration_exclusion.py:109](src/docxaicorrector/document/narration_exclusion.py:109), [narration_coverage.py:48](src/docxaicorrector/text/narration_coverage.py:48)

### 8. P2 — Сохранение ударений в PDF заявлено без соответствующего критерия

**Уверенность высокая.**

FR-002 перечисляет TXT, DOCX и MiniMax. FR-007 добавляет PDF, Anti-regression требует сохранения во всех выходах. Системный тест PDF в 072 прямо использует набор **без combining marks**. Он не доказывает сохранение U+0301 в текстовом слое и его привязку к нужной букве. [073/spec.md:115](specs/073-narration-for-the-ear/spec.md:115), [073/spec.md:136](specs/073-narration-for-the-ear/spec.md:136), [072/test_spec_072_narration_pdf_system.py:4](D:/Temp/claude/wt-072/tests/test_spec_072_narration_pdf_system.py:4)

Нужен критерий для извлечённого PDF-текста с ударениями, включая заголовок, перенос строки и несколько ударений в абзаце. Удаление M* при сравнении сделает такую проверку вакуумной. Поведение конкретного WSL LibreOffice здесь остаётся непроверенным. [072/test_spec_072_narration_pdf_system.py:75](D:/Temp/claude/wt-072/tests/test_spec_072_narration_pdf_system.py:75), [072/test_spec_072_narration_pdf_system.py:135](D:/Temp/claude/wt-072/tests/test_spec_072_narration_pdf_system.py:135)

### 9. P2 — SC-002–SC-004 допускают вакуумную приёмку и смешивают разные причины изменений

**Уверенность высокая.**

- **SC-002** может пройти при пустом или сильно урезанном словаре. Нужны знаменатели для найденных кандидатов, отправленных, принятых, доставленных в блоки и проверенных вхождений. Пропущенное или удалённое вхождение должно учитываться. [073/spec.md:149](specs/073-narration-for-the-ear/spec.md:149)
- **SC-003** может пройти на выборке без омографов. Нужны непустой положительный набор и отдельно число неоднозначных и обычных слов. Требование сценария «слово без неоднозначности знака не получает» также следует согласовать с допускаемыми лишними ударениями. [073/spec.md:83](specs/073-narration-for-the-ear/spec.md:83), [073/spec.md:101](specs/073-narration-for-the-ear/spec.md:101), [073/spec.md:151](specs/073-narration-for-the-ear/spec.md:151)
- **SC-004** сравнивает общий `low_coverage`, хотя новая транслитерация сама меняет буквенные основы относительно исходника. Увеличение счётчика может произойти при правильной работе FR-003. Изоляцию эффекта U+0301 следует проверять парой одинаковых текстов с ударениями и без них, сохранив контрпример с настоящей потерей текста. [073/spec.md:153](specs/073-narration-for-the-ear/spec.md:153), [narration_coverage.py:44](src/docxaicorrector/text/narration_coverage.py:44)

Историческая полная Money имеет базу `24391ce`, три `low_coverage` и 214 неизмеренных абзацев. После неё менялись промпт и исключения. После слияния 072 следует закрепить актуальную базу сравнения и её знаменатель. Старый отчёт годится как историческое свидетельство. [report.json:34](D:/Temp/docxai-research/070-fr009/runs/archive/20261110T074147Z_40074_money_full_standard_translated_ru/audiobook_money_full_standard_translated_report.json:34), [report.json:531](D:/Temp/docxai-research/070-fr009/runs/archive/20261110T074147Z_40074_money_full_standard_translated_ru/audiobook_money_full_standard_translated_report.json:531), [070/spec.md:336](specs/070-audiobook-technical-pass/spec.md:336)

### 10. P2 — FR-006 не доводит новый артефакт до приёмочного раннера

**Уверенность средняя.**

Связь с группой результата, состоянием и экраном задана совместимо с 072. Однако в 072 контракт отдельно требует сохранять новые форматы в каталог канонического прогона, перечислять в `output_artifacts` и сводке. В 073 для MiniMax этот маршрут отсутствует, хотя FR-010 использует именно канонический прогон. Его нужно явно распространить на `.minimax.txt`, словарь чтения и новые счётчики. [073/spec.md:133](specs/073-narration-for-the-ear/spec.md:133), [073/spec.md:141](specs/073-narration-for-the-ear/spec.md:141), [072/spec.md:145](specs/072-narration-docx-pdf/spec.md:145)

Для проверки совместимости достаточно расширить существующие сценарии 072 на отсутствие MiniMax, старый bundle, новый запуск, Stop и очистку группы. Состав опубликованной группы должен определяться успешно собранными форматами, с сохранением существующей гарантии отката при обработанной ошибке. [072/spec.md:151](specs/072-narration-docx-pdf/spec.md:151), [072/runtime/artifacts.py:406](D:/Temp/claude/wt-072/src/docxaicorrector/runtime/artifacts.py:406)

### 11. P3 — В описании измерений есть фактическая ошибка, checklist преждевременно закрыт

**Уверенность высокая.**

В указанном файле пар четвёртый раздел озвучен **«Четыре. Решение…»**. Утверждение спеки **«Глава четыре.»** этому файлу не соответствует. Ссылки на строки остальных четырёх номеров корректны. [073/spec.md:52](specs/073-narration-for-the-ear/spec.md:52), [money_ch3_pairs_all.md:274](D:/Temp/docxai-research/070-fr009/pairs/money_ch3_pairs_all.md:274)

Для TRC и CoR-EU нужен отдельный источник полной книги. В файле пар главы III этих обозначений нет. В полном выводе видны раскрытие TRC словами, «ти-ар-си», «ти-эр-си» и сохранённая латиница `TRC`. Число «три способа» требует определения, какие формы считались и как учтён оставленный латинский вариант. [money_book_tts.txt:361](D:/Temp/docxai-research/070-fr009/pairs/money_book_tts.txt:361), [money_book_tts.txt:1905](D:/Temp/docxai-research/070-fr009/pairs/money_book_tts.txt:1905), [money_book_tts.txt:1945](D:/Temp/docxai-research/070-fr009/pairs/money_book_tts.txt:1945), [money_book_tts.txt:1967](D:/Temp/docxai-research/070-fr009/pairs/money_book_tts.txt:1967)

Флажки «requirements … unambiguous», «all functional requirements have clear acceptance criteria» и «feature meets measurable outcomes» следует пересмотреть после устранения перечисленных неоднозначностей. [checklists/requirements.md:18](specs/073-narration-for-the-ear/checklists/requirements.md:18), [checklists/requirements.md:28](specs/073-narration-for-the-ear/checklists/requirements.md:28)

## Что подтверждено и как принимать

Ссылки раздела «Что есть сейчас» в основном соответствуют коду main. Результаты слуховых проб в таблице согласуются с записями владельца. Журнал подтверждает 13 запросов MiniMax. Значения тишины записаны в RESEARCH, самостоятельно аудио я не перемерял. Успешность ударений подтверждается слуховой записью владельца, транскрипция Whisper ударения не размечает. [073/spec.md:57](specs/073-narration-for-the-ear/spec.md:57), [MiniMax/RESEARCH.md:251](D:/Temp/docxai-research/minimax-tts/RESEARCH.md:251), [MiniMax/RESEARCH.md:270](D:/Temp/docxai-research/minimax-tts/RESEARCH.md:270), [ElevenLabs/RESEARCH.md:186](D:/Temp/docxai-research/elevenlabs-studio/RESEARCH.md:186)

Без платного прогона можно проверить нормализацию, сохранение знаков, невакуумное покрытие, классы остатка, кандидатов и бюджеты, число запросов на подменённом клиенте, поблочную доставку словаря, паузы, равенство TXT, артефакты и состояние. PDF требует отдельного локального WSL-прогона с LibreOffice. Точность выбора ударения моделью и фактическое звучание требуют платной генерации и прослушивания. [073/spec.md:141](specs/073-narration-for-the-ear/spec.md:141), [072/spec.md:174](specs/072-narration-docx-pdf/spec.md:174)

**Полный цикл оправдан** новыми межмодульными контрактами. Разделение разумно по двум независимо принимаемым результатам — подготовка чтения FR-001–004 и экспорт MiniMax FR-005–006. Обязательной необходимости разделять нет. Если оставить одну спеку, стоит отдельно зафиксировать их приёмку и зависимости. Конституция VII допускает полученный из книги словарь как данные прогона при универсальном отборе. В Anti-regression следует добавить точное сопоставление вхождений, контрпримеры потери текста, изоляцию словарей между прогонами и сохранение структурных сигналов. [constitution.md:115](.specify/memory/constitution.md:115), [constitution.md:189](.specify/memory/constitution.md:189), [073/spec.md:170](specs/073-narration-for-the-ear/spec.md:170)

СТРОИТЬ ПОСЛЕ ПРАВОК
