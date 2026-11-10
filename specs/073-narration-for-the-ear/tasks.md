# Tasks: текст для озвучки, который голос читает без ошибок

**Spec**: [spec.md](spec.md) | **Plan**: [plan.md](plan.md) (раздел «Порядок реализации: пакеты работ») |
**Контракты**: [contracts/](contracts/) | **Данные**: [data-model.md](data-model.md), [research.md](research.md) |
**Проверка**: [quickstart.md](quickstart.md)

Tier: полный цикл (Конституция, принцип III). Задачи сгруппированы по пакетам WP-A…WP-K; порядок внутри пакета всегда
один: (A) характеристические / золотые тесты того, что НЕ должно измениться → (B) падающие тесты нового поведения
(анти-вакуум: у каждого сказано, чем доказано, что он падает без правки) → (C) реализация → (D) каноническая проверка
пакета. Пакет владеет ТОЛЬКО перечисленными у него файлами (Конституция VI); правка вне перечня запрещена — нужда в
ней возвращается оркестратору вопросом. Связь с историями спеки: US1 (голос не спотыкается) — WP-A, B, C, D, E, F; US2
(версия для MiniMax) — WP-G, H, J, K, I.

## Формат и общие правила

- `T-<пакет><номер>`; `[P]` — можно параллельно с соседними задачами того же пакета (разные файлы, нет зависимости);
  `[?]` — решение оркестратора/владельца, агент не гадает; `[$]` — платно, только с согласия владельца. Между пакетами
  параллельность задана волнами.
- **База**: `073/integration` от `main` @ `7347bd3`. Ссылки `file:line` плана сверены там; если ветка ушла вперёд —
  сверить заново (Конституция VIII), расхождение — вопрос оркестратору.
- **Каноническая проверка пакета** — одна команда на один selector, selector ДО опций pytest:
  `wsl.exe -d Debian --cd "D:\Temp\claude\wt-073-<slug>" -- bash scripts/test.sh <selector> -q` (`.venv` — симлинк на
  главное дерево). Из Git Bash `$VAR` на границе `wsl.exe` схлопывается — только литеральные пути, без циклов `for`.
  Голый `python` / `.venv-win` / `py -m pytest` запрещены (debug-путь — только с пометкой `debug-only`). Оборванный
  вывод — сначала проблема транспорта; сужать до node selector.
- **Тесты истории** в боковом worktree пропускаются; проверяются в главном дереве (T-Z3). `git` в боковом worktree под
  WSL не работает — коммиты и `git diff --check` из Git Bash в worktree.
- **Конституция VII**: ни в коде, ни в тестах нет текста книг, литералов корпуса, словарей омографов, транслитерации,
  сокращений и чисел; примеры — вымышленные, той же ФОРМЫ (`ABC`, `XyZ-QW`, `Квазибург`, `Zentrix`); правила — по
  свойствам Unicode, роли и уровню.
- **Новый тестовый файл** — строку в `docs/testing/TEST_TIER_INVENTORY.md` добавляет ОРКЕСТРАТОР при слиянии пакета
  (research R16); в worktree пакета гард инвентаря
  (`tests/test_script_contract_static.py::test_inventory_lists_every_top_level_test_file_exactly_once`) красный — пакет
  его не запускает.
- **LF** во всех новых файлах; после правок `git diff --check`. Полные тексты в лог не пишутся.
- Тема коммита пакета: `spec 073: <что сделано>`.

## Волны и зависимости

```text
T-01 (оркестратор): worktrees от 073/integration
волна 1 (параллельно):  WP-A  WP-B  WP-G  WP-J  WP-K          слияние: любой порядок, полный прогон после каждого
волна 2 (параллельно):  WP-C ← A   WP-D ← A   WP-E ← A
волна 3 (параллельно):  WP-F ← D, E   WP-H ← C, D, G, J
волна 4:                WP-I ← F, H
приёмка:                T-Z1…T-Z7 → WP-Y (платно, по согласию владельца)
```

Критический путь: **WP-A → WP-E → WP-F → WP-I**.

## Подготовка (оркестратор)

- [ ] **T-01** Ветка `073/integration` от `main`; worktrees `D:\Temp\claude\wt-073-{forms,prompt,minimax,group,screen}` для
  волны 1 (ветки `073/wp-a-forms`, `073/wp-b-prompt`, `073/wp-g-minimax`, `073/wp-j-result-group`, `073/wp-k-screen`),
  симлинк `.venv` на главное дерево.
- [ ] **T-02** При первом слиянии кода — статус спеки `IN PROGRESS` и абзац спеки 073 в `docs/WHERE_WE_ARE.md` (иначе
  `test_spec_status_consistency` / `test_where_we_are_freshness` красны в главном дереве).

---

## WP-A. Формы текста и лексические сравнения (FR-002, SC-005)

**Ветка**: `073/wp-a-forms` | **Worktree**: `D:\Temp\claude\wt-073-forms` | **Агент**: Sonnet / high |
**Сначала слиты**: ничего | **Владеет**: `src/docxaicorrector/text/narration_forms.py` (нов.),
`src/docxaicorrector/text/narration_coverage.py`, `src/docxaicorrector/text/narration_residue.py` (только
`_is_all_caps_paragraph`, поиск `roman_numerals` и три публичные формы ниже), `src/docxaicorrector/document/narration_exclusion.py`,
`src/docxaicorrector/generation/_generation.py` (только `_normalize_leakage_comparison_text`, `:1462-1463`, и
`_detect_context_leakage`, `:1466-1500`), `tests/test_spec_073_narration_forms.py` (нов.). Решение — research R1;
сущности — `data-model.md` §1.

**A. Характеристика (ДО любой правки, зелёные на `7347bd3`)**
- [ ] **T-A1** Без знаков ничего не меняется: на синтетическом наборе (≥ 20 абзацев: проза, заглавные, римские, адрес,
  цифры, латиница) `paragraph_coverage`, `detect_narration_residue` (классы, счёт, образцы — как ПРОЕКЦИЯ на классы до 073:
  находки фильтруются по кортежу классов `7347bd3`, записанному в тесте литералом, чтобы класс `latin` пакета WP-C не
  противоречил снимку), `is_fragment_without_connected_text`, `_detect_context_leakage` — снимок литералом.
- [ ] **T-A2** Точная сборка видит потерю знака: `assemble_narration_records` с записью `за\u0301мок`, чей собранный
  абзац подменён на `замок`, даёт расхождение (`pipeline/narration_postprocess.py:188-215`, ветвь `mismatch`).

**B. Падающие тесты** (`tests/test_spec_073_narration_forms.py`)
- [ ] **T-A3** [P] `without_combining_marks` — то же, что прежний `_without_combining_marks` (на тех же входах); смещения:
  `stripped[i] == text[offsets[i]]`; `original_span` продлевает конец через следующие M*; `letter_series` не делит
  `за\u0301мок`, режет края-дефисы, берёт `XY-12` целиком только при `digits_inside`, не берёт `ЖЗИ⁷`-надстрочную (падает:
  модуля нет).
- [ ] **T-A4** SC-005: пара синтетических абзацев (≥ 4 слов от 6 букв, ≥ 6 токенов) без знаков и с U+0301 в каждом длинном
  слове — равные `paragraph_coverage`, равный остаток по классам, равный результат протечки при контексте, совпадающем с
  ответом (падает: покрытие 1,0 → 0,4, протечка теряется — research R1). Контрпример: ответ без одного предложения из
  исходника — покрытие ниже порога и со знаками, и без.
- [ ] **T-A5** `А́ЛМАЗ ВЕ́ТЕР`-форма (синтетика: два слова заглавными, знак после первой буквы) → `all_caps`; `I\u0301V` →
  `roman_numerals`; образец остатка — срез ИСХОДНОЙ строки со знаком (падает).
- [ ] **T-A6** Протечка со знаками: возвращённый фрагмент — подстрока исходного ответа со знаками, и
  `_trim_boundary_context_leakage(answer, fragment)` его срезает (падает: `None`).
- [ ] **T-A7** Публичные формы для пакетов C и E: `is_all_caps_paragraph(text) -> bool`, `is_roman_numeral_form(token) ->
  bool` (≥ 2 из `[IVXLCDM]` целиком или все символы Nl), `mask_url_or_domain(text) -> str` (спаны `_URL_OR_DOMAIN` →
  пробелы той же длины, длина строки сохраняется); `has_no_letter_or_digit`, `is_scene_break_text` в
  `document/narration_exclusion.py` (пустая строка и пробелы — не разделитель; `***`, `# %`, `— — —` — разделитель; `1`,
  `I` — нет); `is_latin_letter` в `text/narration_forms.py` (падают: функций нет).

**C. Реализация**
- [ ] **T-A8** `text/narration_forms.py` по `data-model.md` §1; `document/narration_exclusion.py:93-96` — импорт помощника
  под прежним именем, выражение `:167` → `has_no_letter_or_digit`, + `is_scene_break_text`.
- [ ] **T-A9** `text/narration_coverage.py:48-55` — обе стороны без знаков; `text/narration_residue.py:122-130`, `:142-143` —
  поиск по строке без знаков, позиция — исходной строки; три публичные формы.
- [ ] **T-A10** `generation/_generation.py:1462-1500` — нормализация без знаков, токены по строке без знаков, фрагмент —
  срез исходного ответа через `original_span`.

**D. Проверка**
- [ ] **T-A11** Отдельными командами: `tests/test_spec_073_narration_forms.py`, `tests/test_narration_coverage.py`,
  `tests/test_narration_residue.py`, `tests/test_narration_exclusion_070.py`, `tests/test_narration_exclusion_addresses.py`,
  `tests/test_generation.py`, `tests/test_audiobook_pass.py`, `tests/test_spec_070_request_golden.py`. Done: зелёные; T-A1/T-A2
  не правились.

---

## WP-B. Правила промпта (FR-001, FR-003 промпт, FR-005)

**Ветка**: `073/wp-b-prompt` | **Worktree**: `D:\Temp\claude\wt-073-prompt` | **Агент**: **Opus** / high |
**Сначала слиты**: ничего | **Владеет**: `src/docxaicorrector/resources/prompts/operation_audiobook.txt`,
`src/docxaicorrector/resources/prompts/operation_audiobook_repair.txt`, `src/docxaicorrector/resources/prompts/example_audiobook.txt`,
`tests/test_audiobook_prompt.py` (только новые свойства), `tests/test_spec_073_prompt_rules.py` (нов.). Решение — research
R3; контракт — `contracts/prompt-and-glossary.md` §1 (литерал заголовка секции — §2: правило промпта ссылается на него
дословно).

**A. Характеристика**
- [ ] **T-B1** `tests/test_spec_070_request_golden.py` и все гарды `tests/test_audiobook_prompt.py` зелёные до правки (и
  после — без изменения хэшей).

**B. Падающие тесты** (`tests/test_spec_073_prompt_rules.py`; свойства, не фразы)
- [ ] **T-B2** Основной промпт режима: содержит U+0301 хотя бы в одном слове (пример правила); упоминает раздел по его
  литеральному названию из `READING_GLOSSARY_SECTION_HEADER` (без зависимости от модуля WP-E — литерал контракта); нет
  примера ударения «+» перед гласной (`re.search(r"\+[аеёиоуыэюя]", …)` пусто) и нет заглавной гласной внутри строчного
  слова (`[а-яё][АЕЁИОУЫЭЮЯ][а-яё]` пусто) (падает: правил нет).
- [ ] **T-B3** Приоритет латиницы: четыре пункта в порядке «раздел сокращений → сокращение без записи → инициал →
  кириллические как есть» — проверка позиций якорных слов каждого пункта в тексте правила (`index` возрастает); правило
  инициалов 070 («не восстанавливайте имя по памяти») на месте.
- [ ] **T-B4** Правило номера раздела: упоминает заголовок, число и римское число с точкой, в том числе внутри разметки
  выделения в начале заголовка (`**1. …**` — 10 из 46 заголовков полной Money, research R3), порядковое числительное
  среднего рода и запрет добавлять слова (проверка — наличие правила одной строкой с этими свойствами; пример формы
  «Первое.» допустим как иллюстрация, не как список чисел).
- [ ] **T-B5** ОТРЕНДЕРЕННЫЙ промпт исправления (`load_system_prompt(operation="audiobook", prompt_variant="repair")` —
  вариант читает свой файл, `core/config.py:1773`): называет латиницу среди остатка; содержит правило ударения (U+0301 в
  слове правила, нет «+» перед гласной, нет заглавной гласной внутри строчного слова); тот же приоритет латиницы из
  четырёх пунктов в порядке (проверка T-B3 на этом тексте); ссылается на раздел сокращений; «как есть» — только
  кириллические (падает: в инструкциях исправления этого нет).
- [ ] **T-B6** Пример: одна пара — латинское название в исходнике и кириллица в результате, U+0301 в результате; одна пара
  — заголовок `## **N. …**` (синтетический) и результат в форме «Первое. …»; существующие гарды примеров
  (`tests/test_audiobook_prompt.py:117-139`) зелёные.

**C. Реализация**
- [ ] **T-B7** Правки трёх файлов промпта по `contracts/prompt-and-glossary.md` §1; правила 1, 3, 4, 6, 7 по смыслу не
  меняются; нумерация правил — сквозная.

**D. Проверка**
- [ ] **T-B8** Отдельными командами: `tests/test_spec_073_prompt_rules.py`, `tests/test_audiobook_prompt.py`,
  `tests/test_spec_070_request_golden.py`, `tests/test_audiobook_language_free.py`, `tests/test_config.py`. Done: зелёные.

---

## WP-G. Текст для MiniMax (FR-007, SC-006)

**Ветка**: `073/wp-g-minimax` | **Worktree**: `D:\Temp\claude\wt-073-minimax` | **Агент**: Sonnet / high |
**Сначала слиты**: ничего | **Владеет**: `src/docxaicorrector/pipeline/narration_minimax.py` (нов.),
`tests/test_spec_073_narration_minimax.py` (нов.). Решение — research R9; сущности и таблица — `data-model.md` §7;
метки — `contracts/prompt-and-glossary.md` §4. Вход — `NarrationMinimaxGroupLike` (Protocol) и настоящий план 072
(`build_narration_document_plan`, тесты строят свои группы с полем `after_scene_break`); от WP-D не зависит.

**B. Падающие тесты** (модуля нет — все падают)
- [ ] **T-G1** Таблица `data-model.md` §7 — каждая строка отдельным параметризованным случаем: метки в конце групп,
  `pause_counts`, `pauses_by_group`.
- [ ] **T-G2** Равенство: удаление вставленных меток (по `pauses_by_group`, с конца каждой группы) =
  `"\n\n".join(g.text for g in groups)` побайтно — на наборе с U+0301, `\n` внутри группы, `#` в начале тела.
  Отрицательный контроль той же функцией сравнения: лишний пробел перед меткой — не равно.
- [ ] **T-G3** Нет двух меток подряд (регулярное выражение `#>\s*<#` пусто) на всех случаях; последняя группа — без метки;
  меток ровно `sum(pause_counts.values())`.
- [ ] **T-G4** Анти-вакуум серий: `H2, H1, B` — нет метки после `H2`; тот же набор с телом между `H2` и `H1` — метка после
  `H2` есть (`<#0.8#>`).
- [ ] **T-G5** Шаги плана и групп не сходятся (группа-заголовок из двух записей, подложенная вручную) → исключение
  `ValueError` наружу.

**C. Реализация**
- [ ] **T-G6** `pipeline/narration_minimax.py` по `data-model.md` §7. Без I/O, без Streamlit, без импорта `docx`.

**D. Проверка**
- [ ] **T-G7** `tests/test_spec_073_narration_minimax.py`, `tests/test_spec_072_narration_document.py`. Done: зелёные.

---

## WP-J. Член группы и bundle (FR-008, файлы)

**Ветка**: `073/wp-j-result-group` | **Worktree**: `D:\Temp\claude\wt-073-group` | **Агент**: Sonnet / medium |
**Сначала слиты**: ничего | **Владеет**: `src/docxaicorrector/runtime/artifacts.py`,
`src/docxaicorrector/runtime/artifact_retention.py`, `src/docxaicorrector/processing/processing_runtime.py` (только
`_normalize_narration_exports`, `:1657-1675`), `tests/test_spec_073_result_group.py` (нов.),
`tests/test_spec_072_state_bundle.py` (только три равенства всего словаря `:74`, `:92`, `:120` — добавить ключ
`minimax_text`; ревью плана Codex, находка 5). Решение — research R10; контракт — `contracts/result-and-screen.md` §1–2.

**A. Характеристика**
- [ ] **T-J1** Без нового аргумента: состав группы, имена и `artifact_paths` `write_ui_result_artifacts` для аудиокниги с
  DOCX/PDF и для перевода — снимок, зелёный до и после; `tests/test_spec_072_result_group.py` — зелёный без изменений;
  `tests/test_spec_072_state_bundle.py` — меняется ТОЛЬКО на новый ключ (`"minimax_text": None` в трёх ожидаемых словарях),
  остальные ожидания побайтно прежние.

**B. Падающие тесты** (`tests/test_spec_073_result_group.py`)
- [ ] **T-J2** `narration_minimax_text="…<#1.5#>…"` → файл `<stem>.tts.minimax.txt` с этим текстом (UTF-8, LF), ключ
  `tts_minimax_path`; `None` или `""` → нет ни файла, ни ключа (падает: аргумента нет).
- [ ] **T-J3** Сбой записи члена `.tts.minimax.txt` (подмена записи временного файла → `OSError`) — в каталоге не остаётся
  ни одного файла группы, ни временных.
- [ ] **T-J4** Хранение: группа с `.tts.minimax.txt` старше срока или сверх числа удаляется ЦЕЛИКОМ, вместе с ним
  (падает: файл уходит в «passthrough», `runtime/artifact_retention.py:199`, `:212`); ключ группы
  `x.result.tts.minimax.txt` → `x`; `x.result.tts.txt` по-прежнему → `x`.
- [ ] **T-J5** `_normalize_narration_exports({..., "minimax_text": "t"})` сохраняет `minimax_text`; не-`str` и `""` →
  `None`; лишние ключи отброшены, четыре ключа 072 как были; три равенства `tests/test_spec_072_state_bundle.py:74`,
  `:92`, `:120` обновлены на пятый ключ и зелёные.

**C. Реализация**
- [ ] **T-J6** `runtime/artifacts.py:366-461` (аргумент, путь, член группы, ключ); `runtime/artifact_retention.py:90-99`
  (+`.result.tts.minimax.txt`, длинный суффикс раньше); `processing/processing_runtime.py:1657-1675`.

**D. Проверка**
- [ ] **T-J7** Отдельными командами: `tests/test_spec_073_result_group.py`, `tests/test_spec_072_result_group.py`,
  `tests/test_spec_072_state_bundle.py`, `tests/test_runtime_artifacts.py`, `tests/test_session_artifact_isolation.py`,
  `tests/test_processing_runtime.py`. Done: зелёные.

---

## WP-K. Кнопка MiniMax (FR-008, экран)

**Ветка**: `073/wp-k-screen` | **Worktree**: `D:\Temp\claude\wt-073-screen` | **Агент**: Sonnet / medium |
**Сначала слиты**: ничего (ключ bundle — `contracts/result-and-screen.md` §2, фиксирован) | **Владеет**:
`src/docxaicorrector/ui/_ui.py`, `src/docxaicorrector/ui/locales/ru.json`, `src/docxaicorrector/ui/locales/en.json`,
`tests/test_spec_073_result_screen.py` (нов.). Контракт — `contracts/result-and-screen.md` §3.

**A. Характеристика**
- [ ] **T-K1** `tests/test_spec_072_result_screen.py` и `tests/test_ui.py` зелёные до и после без изменений (bundle без
  `minimax_text` — экран 072 побайтно).

**B. Падающие тесты** (`tests/test_spec_073_result_screen.py`; рендер с двойником `st`)
- [ ] **T-K2** Аудиокнига со всеми форматами: строка «Текст для озвучки» — DOCX, PDF, TXT, MiniMax в этом порядке; у
  MiniMax имя `<stem>.tts.minimax.txt`, MIME `text/plain`, `type="secondary"`, `width="stretch"` (падает: кнопки нет).
- [ ] **T-K3** `minimax_text=None` — три кнопки 072, строки причины нет; заблокированная выдача — метка
  `result.blocked_download_narration_minimax`; перевод/редактура — кнопок MiniMax нет.
- [ ] **T-K4** Ключи `result.narration_minimax`, `result.blocked_download_narration_minimax` — в обоих каталогах; в `ui/`
  нет `use_container_width`.

**C. Реализация**
- [ ] **T-K5** `ui/_ui.py`: `_build_narration_minimax_filename` (рядом с `:92-101`), кнопка в `_render_audiobook_downloads`
  (`:1111-1196`) после TXT. Ветвь перевода/редактуры не трогать.
- [ ] **T-K6** [P] Локали.

**D. Проверка**
- [ ] **T-K7** Отдельными командами: `tests/test_spec_073_result_screen.py`, `tests/test_spec_072_result_screen.py`,
  `tests/test_ui.py`, `tests/test_ui_i18n.py`. Done: зелёные. Браузер — после слияния всего (T-Z4).

---

## WP-C. Класс остатка `latin` (FR-003 детектор, SC-001 форма, SC-007)

**Ветка**: `073/wp-c-latin` | **Worktree**: `D:\Temp\claude\wt-073-latin` | **Агент**: Sonnet / medium |
**Сначала слиты**: WP-A | **Владеет**: `src/docxaicorrector/text/narration_residue.py` (класс `latin`),
`tests/test_narration_residue.py` (только множества классов, `:114-116`), `tests/test_spec_073_latin_residue.py` (нов.).
Решение — research R2; сущности — `data-model.md` §2.

**A. Характеристика**
- [ ] **T-C1** На наборе T-A1 без латиницы — классы, счёт и образцы прежние (снимок WP-A зелёный).

**B. Падающие тесты** (`tests/test_spec_073_latin_residue.py`)
- [ ] **T-C2** `Zentrix и Quorvel Labs` → `latin`, `count == 3`; `XyZ-QW` — одна единица; `Квазибургa` (кириллица с латинской
  буквой-двойником) — одна единица; `кв\u0301азар` без латиницы — нет класса (падает: класса нет).
- [ ] **T-C3** Анти-вакуум вычитаний: строка с адресом `zentrix.example` И словом `Quorvel` — ровно одна единица (адрес
  замаскирован, слово считается); `глава IV, раздел Quorvel` — одна единица (римское не латиница, слово — да); одиночная
  `I` — латиница (осознанно, research R2).
- [ ] **T-C4** `latin` в `REPAIRABLE_RESIDUE_CLASSES`; порядок классов — после `tag_form`; `tests/test_narration_residue.py:114-116`
  обновлён осознанно (множества с `latin`).
- [ ] **T-C5** SC-007: `finalize_audiobook_block` + настоящий `repair_block_residue` (через `_audiobook_repair_call` не нужно —
  прямой вызов с подменённым клиентом, у которого `with_options(max_retries=0)` возвращает считающий транспорт): блок с
  остатком `digits`, `all_caps` и `latin` в трёх абзацах → ровно ОДИН оплачиваемый вызов: успешная первая отправка —
  ровно один запрос транспорта; обычное исключение транспорта не повторяется (одна отправка, `needs_review`); повторная
  отправка допустима только после отклонённого запроса без ответа (FR-003; отдельным случаем не проверяется — это
  поведение `request_text_completion`, не 073); ответ без латиницы → `residue_after` пусто; ответ с латиницей →
  `needs_review`, второго вызова нет.

**C. Реализация**
- [ ] **T-C6** `text/narration_residue.py`: `RESIDUE_LATIN`, `latin_units` по `data-model.md` §2, место в кортежах, докстринг
  модуля (класс исправим, единица — серия).

**D. Проверка**
- [ ] **T-C7** Отдельными командами: `tests/test_spec_073_latin_residue.py`, `tests/test_narration_residue.py`,
  `tests/test_audiobook_repair.py`, `tests/test_audiobook_pass.py`, `tests/test_spec_073_narration_forms.py`. Done: зелёные.

---

## WP-D. Разделитель сцены и объявления состояния (FR-006, SC-006)

**Ветка**: `073/wp-d-scene-breaks` | **Worktree**: `D:\Temp\claude\wt-073-breaks` | **Агент**: **Opus** / high |
**Сначала слиты**: WP-A | **Владеет**: `src/docxaicorrector/pipeline/audiobook_pass.py` (только `register_audiobook_block`,
`:533-564`, и константа `NARRATION_PARAGRAPH_KINDS`), `src/docxaicorrector/pipeline/narration_postprocess.py`,
`src/docxaicorrector/pipeline/contracts.py` (все объявления `data-model.md` §5), `tests/test_spec_073_scene_breaks.py` (нов.).
Решение — research R8; сущности и таблица — `data-model.md` §5–6.

**A. Характеристика**
- [ ] **T-D1** Золотой SHA-256 `.tts.txt` 072 (`tests/test_spec_072_narration_groups.py`) и `tests/test_audiobook_pass.py`,
  `tests/test_narration_markdown.py` — зелёные до и после без изменений; набор без разделителей даёт те же группы и
  склейки.

**B. Падающие тесты** (`tests/test_spec_073_scene_breaks.py`)
- [ ] **T-D2** `register_audiobook_block` пишет `state.narration_paragraph_kinds` по порядку абзацев блока: `narrated`,
  `scene_break` (`fragment` + `is_scene_break_text`), `excluded` (иные причины; `fragment` с буквами) — на двух блоках подряд
  (падает: поля нет).
- [ ] **T-D3** Таблица `data-model.md` §6 — каждая строка параметризованным случаем через чистую
  `scene_break_before_ids` и через `_build_narration_text` на двойнике состояния (виды из регистрации, записи с текстами):
  отметки, `NarrationGroup.after_scene_break`, разрешена ли склейка.
- [ ] **T-D4** Анти-вакуум запрета склейки: пара `B1` (без точки) + `B2` (со строчной) без разделителя — склеена (как
  сейчас); та же пара с `***` между ними — две группы, `after_scene_break` у второй; `text == "\n\n".join(g.text …)`.
- [ ] **T-D5** Объявления: `ProcessingState()` имеет `narration_paragraph_kinds == []`, `audiobook_reading_glossary is None`,
  `audiobook_reading_glossary_block_indexes == set()`; `ResultArtifactWriter` принимает `narration_minimax_text` (проверка
  сигнатуры протокола).

**C. Реализация**
- [ ] **T-D6** `pipeline/contracts.py` — объявления; `pipeline/audiobook_pass.py:533-564` — виды абзацев (исходник —
  `sources[position]`, уже читается для исключённых).
- [ ] **T-D7** `pipeline/narration_postprocess.py`: `NarrationGroup.after_scene_break` (последним), `scene_break_before_ids`,
  параметр `assemble_narration_records`, расчёт в `_build_narration_text` (`:236-270`).

**D. Проверка**
- [ ] **T-D8** Отдельными командами: `tests/test_spec_073_scene_breaks.py`, `tests/test_spec_072_narration_groups.py`,
  `tests/test_audiobook_pass.py`, `tests/test_narration_markdown.py`, `tests/test_spec_072_narration_document.py`,
  `tests/test_document_pipeline.py`. Done: зелёные; T-D1 не правился.

---

## WP-E. Словарь чтения: ядро (FR-004, SC-002 механизм, SC-007)

**Ветка**: `073/wp-e-glossary` | **Worktree**: `D:\Temp\claude\wt-073-glossary` | **Агент**: **Opus** / high |
**Сначала слиты**: WP-A | **Владеет**: `src/docxaicorrector/pipeline/reading_glossary.py` (нов.),
`src/docxaicorrector/resources/prompts/audiobook_reading_glossary.txt` (нов.), `src/docxaicorrector/core/model_accounting.py`
(только константа стадии), `src/docxaicorrector/pipeline/glossary_phase.py` (только необязательный параметр стадии у
`_stage_usage`, `:147-161`), `src/docxaicorrector/generation/_generation.py` (только вынос `retry_backoff_seconds` из
цикла блока, `:3606`; после WP-A), `tests/test_spec_073_reading_glossary.py` (нов.). Решения — research R4–R7 (R5 — в
редакции решения владельца 2026-11-10: пакеты, повторы как у блока, повторный запрос, сбой прогона при недоступности);
сущности — `data-model.md` §4; контракт — `contracts/prompt-and-glossary.md` §2–3, `contracts/events.md`.

**A. Характеристика**
- [ ] **T-E1** `tests/test_glossary_pass.py`, `tests/test_document_pipeline.py` (фаза 063), `tests/test_spec_070_request_golden.py`,
  `tests/test_generation.py` (цикл повторов блока: те же паузы после выноса `retry_backoff_seconds`) — зелёные до и после;
  `_stage_usage()` без аргумента возвращает то же, что раньше (стадия `glossary_extraction`); две стадии в одном
  журнале учёта — `_stage_usage()` и `_stage_usage(stage_name="audiobook_reading_glossary")` возвращают каждая своё.

**B. Падающие тесты** (`tests/test_spec_073_reading_glossary.py`; модуля нет — все падают)
- [ ] **T-E2** Форма кандидата: `ABC`, `AbC-DE`, `XY-12`, `ЖЗИ`, `ЖЗИ⁷` → `ЖЗИ` — кандидаты; `Abc`, `aBc`, `IV`, `MMXX`,
  единица внутри `www.abc.example`, любое слово абзаца целиком заглавными — нет; точное написание (`ABC` ≠ `Abc`).
- [ ] **T-E3** Отбор: частота desc, затем первое появление; 201 различный кандидат → 200 `sent`, 1 отброшен пределом
  (самый редкий/поздний); `context` ≤ 160 знаков и содержит первое вхождение.
- [ ] **T-E4** Пакеты и повторы (подменённый `request_text_completion_fn`, считающий вызовы, и `sleep_fn`, записывающий
  паузы): 85 кандидатов → пакеты 40 / 40 / 5 и ровно 3 вызова при разборчивых ответах; успешная первая отправка пакета —
  ровно один вызов; `usage_stage == "audiobook_reading_glossary"`, `should_stop` передан, клиент — тот, что передан (не
  `with_options(max_retries=0)`); 0 вызовов при пустом списке (`no_candidates`) и при Stop до шага или перед вторым
  пакетом (`stopped`, вызовов ровно 1).
- [ ] **T-E4a** Повтор сбойного пакета САМ: второй пакет отвечает повторяемой ошибкой (`status_code=503`) один раз, затем
  ответом → вызовов 4 (пакеты 1 и 3 — по одному), `retry_count == 1`, пауза `retry_backoff_seconds(1)`; неразборчивый
  ответ (нет JSON) один раз — тоже повтор; обрезанный ответ — бюджет растёт (`_boost_request_output_budget`); обычное
  исключение, не признанное повторяемым, — без повтора, сразу недоступность (падает: модуля нет).
- [ ] **T-E4b** Повторный запрос: первый проход оставил 3 кандидата без чтения (один не отвечен, два отклонены формой) →
  ровно один дополнительный пакет из этих трёх; ответ на него принят → `unresolved_count == 0`, `rerequested_count == 3`;
  если и он оставил один без чтения — `unresolved_count == 1`, третьего запроса нет, статус `built`.
- [ ] **T-E4c** Недоступность: пакет исчерпал `max_retries` попыток повторяемой ошибкой → `ReadingGlossaryUnavailable`
  (`reason`, `batch_index`, `attempts == max_retries`); артефакт с принятыми до сбоя пакетами записан; ERROR
  `audiobook_reading_glossary_failed`; статусов `partial` / `empty` / `failed` у результата нет (анти-вакуум: тот же сценарий
  с ответом на последней попытке — исключения нет, `built`).
- [ ] **T-E5** Разбор и уровни: все пять отказов `data-model.md` §4 (каждый отдельным случаем); полный ответ — INFO
  `audiobook_reading_glossary_built`; `unresolved_count > 0` — дополнительно WARNING `audiobook_reading_glossary_unresolved`
  (`review_data=True`); недоступность — ERROR (проверка уровня у двойника `log_event`); в событиях нет написаний и чтений.
- [ ] **T-E6** Артефакт: пишется через подменённый `write_artifact_fn` с `schema`, `run_id`, кандидатами (`sent`,
  `rerequested`, `resolved`), записями, `unresolved`, пакетами (`pass`, `size`, `attempts`), отказами, usage; не пишется
  без вызова; путь — в событии `audiobook_reading_glossary_built` (или `_failed`).
- [ ] **T-E7** `reading_section_for_block`: заголовок — литерал контракта; только записи, чьи кандидаты есть в переданных
  текстах, в порядке первого появления; нет таких — `""`; запись, принятая для другого блока, отсутствует (два вызова с
  разными текстами — разные секции, функция без состояния); бюджет 2 000 знаков → `- ...`.
- [ ] **T-E8** `run_reading_glossary_phase` на двойниках контекста/состояния: операция `translate`/`edit` — ничего не
  делает и не зовёт клиент; `audiobook` — берёт только озвучиваемые абзацы (`narration_exclusion_reasons[i] is None`),
  передаёт `max_retries=context.max_retries`, пишет `state.audiobook_reading_glossary`, контекст не меняется и
  возвращается `None`; при `ReadingGlossaryUnavailable` — `present_error("audiobook_reading_glossary_failed", …)`,
  `emit_state(last_error=…, latest_docx_bytes=None)`, `emit_failed_result_fn(...)` вызваны (двойники) и их исход
  возвращён — тот же набор, что `handle_block_generation_failure` (`pipeline/block_failures.py:135-243`), без
  `persist_terminal_job_result`.

**C. Реализация**
- [ ] **T-E9** `core/model_accounting.py` — `STAGE_AUDIOBOOK_READING_GLOSSARY`; `pipeline/glossary_phase.py:147` —
  `_stage_usage(stage_name: str = STAGE_GLOSSARY_EXTRACTION)` (локальная `stage` внутри уже занята);
  `generation/_generation.py:3606` — `retry_backoff_seconds(attempt)`, цикл блока зовёт её.
- [ ] **T-E10** `pipeline/reading_glossary.py` по `data-model.md` §4 — переиспользуя `request_text_completion`,
  `is_retryable_error`, `_is_non_completed_response_error`, `_is_incomplete_response_error`, `_boost_request_output_budget`,
  `retry_backoff_seconds`, `_request_envelope`, `glossary_max_output_tokens`, `_load_json_object`,
  `render_glossary_prompt_section`, `_write_run_glossary_artifact`, `_stage_usage` (research R5, таблица). Ни одной копии.
- [ ] **T-E11** [P] `resources/prompts/audiobook_reading_glossary.txt` (`contracts/prompt-and-glossary.md` §3); без
  примеров из корпуса.

**D. Проверка**
- [ ] **T-E12** Отдельными командами: `tests/test_spec_073_reading_glossary.py`, `tests/test_glossary_pass.py`,
  `tests/test_document_pipeline.py`, `tests/test_spec_070_request_golden.py`, `tests/test_audiobook_repair.py`,
  `tests/test_generation.py`. Done: зелёные.

---

## WP-F. Проводка словаря и доставка секции (FR-004, SC-007)

**Ветка**: `073/wp-f-delivery` | **Worktree**: `D:\Temp\claude\wt-073-delivery` | **Агент**: **Opus** / high |
**Сначала слиты**: WP-D, WP-E | **Владеет**: `src/docxaicorrector/pipeline/setup.py`, `src/docxaicorrector/pipeline/_pipeline.py`
(только проводка фазы, `:487`, обёртка по образцу `:781-795`), `src/docxaicorrector/pipeline/block_execution.py`
(`_generate_block_chunk` — части, `:1266-1291`; `_audiobook_repair_call`, `:1519-1569`; передача `payload` из
`finalize_audiobook_block_for_delivery`, `:1603-1605`), `tests/test_spec_073_reading_glossary_delivery.py` (нов.).
Решения — research R6, R7; контракт — `contracts/prompt-and-glossary.md` §2.

**A. Характеристика**
- [ ] **T-F1** Аудиокнига без словаря (`state.audiobook_reading_glossary is None`) и блок без записей: аргумент
  `system_prompt` у `generate_markdown_block` и у исправления — побайтно прежний (снимок); перевод/редактура — фаза
  словаря не вызывается (двойник считает), промпт прежний (`tests/test_spec_070_request_golden.py`).

**B. Падающие тесты** (`tests/test_spec_073_reading_glossary_delivery.py`)
- [ ] **T-F2** SC-007, реальные аргументы: два блока аудиокниги через `execute_processing_block` (или `_generate_block_chunk`)
  с подменённым `generate_markdown_block`; словарь с записями `ABC` (только в блоке 1) и `XYZ` (только в блоке 2): промпт
  блока 1 содержит `- ABC -> …` и не содержит `XYZ`; блока 2 — наоборот (падает: секции нет).
- [ ] **T-F3** Исправление блока 1 (остаток в одном абзаце): системный промпт исправления оканчивается той же секцией,
  что основной запрос блока 1, побайтно; записей блока 2 в нём нет.
- [ ] **T-F4** `state.audiobook_reading_glossary_block_indexes` = {1} (блок 2 без записей не учтён; повторный
  `_generate_block_chunk` блока 1 не удваивает счёт).
- [ ] **T-F5** `execute_processing_run`: фаза словаря вызвана ровно один раз, после фазы 063 и до первого блока (порядок
  вызовов двойников); Stop, взведённый в фазе, — блоков не выполняется, итог «остановлено».
- [ ] **T-F5a** Недоступная модель словаря (двойник `request_text_completion_fn` всегда отвечает повторяемой ошибкой):
  `execute_processing_run` возвращает итог «ошибка», `run_block_processing_phase_fn` НЕ вызван, `last_error` в состоянии,
  `latest_docx_bytes is None`, выдачи нет — те же наблюдаемые следствия, что у неисправимого вызова блока аудиокниги
  (сравнить с прогоном, где падает вызов блока 1, на том же двойнике эмиттеров). Анти-вакуум: доступная модель — блоки
  выполняются, итог успешен.

**C. Реализация**
- [ ] **T-F6** `pipeline/setup.py:356-406` — параметр `run_reading_glossary_phase_fn`, вызов после `:389-399`; не-`None`
  исход фазы возвращается сразу, как `block_phase_outcome` (`:400-406`); `pipeline/_pipeline.py` — обёртка и проводка
  (передаёт `emit_failed_result_fn`).
- [ ] **T-F7** `pipeline/block_execution.py`: `_audiobook_reading_section(state, payload)`; часть в `_generate_block_chunk`
  (только `audiobook`); `_audiobook_repair_call(..., payload)` дописывает секцию к промпту исправления через
  `_combine_system_prompt_with_block_focus`.

**D. Проверка**
- [ ] **T-F8** Отдельными командами: `tests/test_spec_073_reading_glossary_delivery.py`, `tests/test_document_pipeline.py`,
  `tests/test_audiobook_pass.py`, `tests/test_audiobook_repair.py`, `tests/test_spec_070_request_golden.py`,
  `tests/test_generation_request_profile.py`. Done: зелёные.

---

## WP-H. Поздний этап: MiniMax, писатель, учёт (FR-007 интеграция, FR-008, FR-009, FR-010)

**Ветка**: `073/wp-h-late-phase` | **Worktree**: `D:\Temp\claude\wt-073-late` | **Агент**: **Opus** / high |
**Сначала слиты**: WP-C, WP-D, WP-G, WP-J | **Владеет**: `src/docxaicorrector/pipeline/narration_exports.py`,
`src/docxaicorrector/pipeline/late_phases.py`, `src/docxaicorrector/pipeline/audiobook_pass.py` (только поле записи
`source_latin_unit_count`, его счёт в `finalize_audiobook_block`, `audiobook_narration_summary` `:617-672`),
`tests/test_spec_073_late_phase.py` (нов.), `tests/test_late_phases_finalize_gate_persistence.py` (только если ожидания
писателя меняются). Решения — research R9–R11; контракты — `contracts/events.md`, `contracts/result-and-screen.md` §2;
сущности — `data-model.md` §3, §8.

**A. Характеристика**
- [ ] **T-H1** Перевод/редактура через поздний этап с двойниками: аргументы `emit_state` и писателя — снимок (нет
  `narration_minimax_text`), зелёный до и после; `tests/test_spec_072_late_phase_exports.py` — зелёный без изменений.

**B. Падающие тесты** (`tests/test_spec_073_late_phase.py`; записи → `_build_narration_text` → поздний этап, писатель и
экспорт PDF подменены)
- [ ] **T-H2** SC-006 на позднем этапе: синтетический набор (серия `2 → 1`, подзаголовки, `***` между телом, U+0301, `\n`
  внутри) → `latest_narration_exports.minimax_text` без меток == `latest_narration_text` побайтно; писатель получил
  `narration_minimax_text`; метки по `data-model.md` §7 (падает: ключа нет).
- [ ] **T-H3** FR-009: U+0301 побайтно в `.tts.txt`, в абзацах `.tts.docx` (открыть байты) и в `.tts.minimax.txt` одного
  прогона.
- [ ] **T-H4** `build_minimax_text` бросает → WARNING `audiobook_narration_minimax_failed`, `minimax_text=None`, TXT/DOCX/PDF
  выданы; рендерер DOCX бросает → MiniMax всё равно собран.
- [ ] **T-H5** FR-010: поля `ui_audiobook_artifact_saved` по `contracts/events.md` — все новые ключи всегда; прежние ключи
  070/072 на месте; `stress_mark_count` и на 1 000 слов по синтетике; `latin_source_unit_count` = сумма по записям (запись
  с латиницей в исходнике и без — анти-вакуум); `scene_break_count`; поля словаря из `state.audiobook_reading_glossary`,
  включая `rerequested_count`, `unresolved_count`, `batch_count`, `call_count`, `retry_count` (`None` → `not_applicable` и
  нули); в событии нет текстов абзацев и чтений.

**C. Реализация**
- [ ] **T-H6** `pipeline/narration_exports.py:61-199` — `minimax`, `minimax_error`, `state_value` (+`minimax_text`),
  `event_fields` (+поля), событие сбоя.
- [ ] **T-H7** `pipeline/late_phases.py:1439-1466` — `narration_minimax_text` писателю; `pipeline/audiobook_pass.py` — поле
  записи, счёт, сводка.

**D. Проверка**
- [ ] **T-H8** Отдельными командами: `tests/test_spec_073_late_phase.py`, `tests/test_spec_072_late_phase_exports.py`,
  `tests/test_spec_072_exports_system.py -m system_deps`, `tests/test_late_phases_finalize_gate_persistence.py`,
  `tests/test_audiobook_pass.py`, `tests/test_document_pipeline.py`, `tests/test_spec_070_request_golden.py`. Done: зелёные.

---

## WP-I. Раннер, гард событий, документы (FR-008 раннер)

**Ветка**: `073/wp-i-runner-docs` | **Worktree**: `D:\Temp\claude\wt-073-runner` | **Агент**: Sonnet / medium (документы —
можно Haiku) | **Сначала слиты**: WP-F, WP-H | **Владеет**: `tests/artifacts/real_document_pipeline/run_lietaer_validation.py`,
`tests/test_real_document_pipeline_validation.py`, `scripts/_list_log_events.py`, `docs/LOGGING_AND_ARTIFACT_RETENTION.md`,
`AGENTS.md` (только раздел «UI result artifacts», `:462-467`), `README.md` (`:512`), `docs/WORKFLOW_AND_IMAGE_MODES.md`
(`:145`). Решение — research R12; контракт — `contracts/events.md`.

**B. Падающие тесты** (`tests/test_real_document_pipeline_validation.py`)
- [ ] **T-I1** `_SPEC_073_LOG_EVENTS` = четыре новых события (`contracts/events.md`) + `ui_audiobook_artifact_saved`: каждое эмитится в `src/` и
  зарегистрировано в документе логирования; `_SPEC_073_NEW_UI_ARTIFACT_FIELDS` — все ключи `contracts/events.md`
  перечислены в §5.5 (по образцу `:8036-8074`).
- [ ] **T-I2** Отчёт на синтетическом логе и состоянии: `narration_artifact` несёт новые поля; строки сводки
  `narration_scene_break_count=…`, `narration_minimax_status=…` (без удвоения префикса); `output_artifacts.tts_minimax_path`,
  `latest_tts_minimax_path`, `reading_glossary_path`; строка цены стадии `audiobook_reading_glossary`; нет события —
  `not_reported`, не 0.
- [ ] **T-I3** Раннер пишет `<basename>.tts.minimax.txt` из `state["latest_narration_exports"]["minimax_text"]` и копию
  артефакта словаря (путь из `audiobook_reading_glossary_built`, а в прогоне, упавшем на словаре, — из
  `audiobook_reading_glossary_failed`) в каталог прогона и `latest`; без ключа / без события — пути `null`, исключения нет.

**C. Реализация**
- [ ] **T-I4** Раннер (`:5096-5121`, `:1596-…`, `:5051-5093`, `:5209`, `:6648-6669`, `:6933-6935`, образец копии `:4913-4933`).
- [ ] **T-I5** [P] `scripts/_list_log_events.py` — `TARGETS` += `pipeline/reading_glossary.py`.
- [ ] **T-I6** [P] Документы: `docs/LOGGING_AND_ARTIFACT_RETENTION.md` — §3.13 (четыре события), §5.5 (поля), retention
  `.run/ui_results/` (`.result.tts.minimax.txt` в группе), артефакт словаря в семье `.run/run_glossaries/`, Changelog;
  AGENTS.md «UI result artifacts» (`:464-466`) — `.result.tts.minimax.txt`, `tts_minimax_path`; README (`:512`) и
  `docs/WORKFLOW_AND_IMAGE_MODES.md` (`:145`) — четвёртый формат озвучки.

**D. Проверка**
- [ ] **T-I7** Отдельными командами: `tests/test_real_document_pipeline_validation.py`, `tests/test_agent_contract_consistency.py`,
  `tests/test_documentation_links.py`, `tests/test_script_contract_static.py` (кроме гарда инвентаря). Done: зелёные.

---

## Приёмка (оркестратор)

- [ ] **T-Z1** Слияния в `073/integration`: волна 1 (A, B, G, J, K — любой порядок), волна 2 (C, D, E), волна 3 (F, H), I.
  Каждый перенос — на свежую интеграционную ветку; при каждом слиянии — строки новых тестов пакета в
  `docs/testing/TEST_TIER_INVENTORY.md` (`## Unit-Contract`).
- [ ] **T-Z2** После КАЖДОГО слияния — полный прогон в ГЛАВНОМ дереве:
  `wsl.exe -d Debian --cd "D:\Work\Projects\DocxAICorrector" -- bash scripts/test.sh tests/ -q`; перед «всё зелёное» —
  `git status --porcelain` пуст, `git diff --check` чист. Финальное user-visible доказательство перед слиянием в `main` —
  задача VS Code `Run Full Pytest` (AGENTS.md «Финальная верификация и CI»); если путь задачи оркестратору недоступен —
  сказать это прямо в отчёте, доказательством служит shell-прогон выше.
- [ ] **T-Z3** Гарды в главном дереве, каждый отдельной командой: `tests/test_spec_status_consistency.py`,
  `tests/test_where_we_are_freshness.py`, `tests/test_documentation_links.py`, `tests/test_script_contract_static.py`,
  `tests/test_layer_boundaries.py`, `tests/test_typecheck.py` (≥ 180 с; новых ошибок нет).
- [ ] **T-Z4** [?] Экран в браузере (`quickstart.md` §5): кнопка «TXT для MiniMax», порядок, растяжение, имя скачанного
  файла, метки в нём. Нужен платный запуск главы (≈ 0,03 $) — с согласия владельца; без него сказать прямо, что экран
  проверен только рендер-тестом WP-K.
- [ ] **T-Z5** Расширенное ревью Codex `gpt-6-astra`, `--sandbox read-only` (SC-009), по рецепту AGENTS.md («Обязательная
  приёмка оркестратора») ДО слияния в `main`: самый свежий `codex.exe` (`Sort-Object LastWriteTime -Descending`), промпт
  файлом через stdin, ответ в файл, в фоне. Объём — все затронутые поверхности: модули с изменённым hunk целиком (список из
  `git diff --stat 7347bd3..<head>`), прямые вызывающие/вызываемые (`block_execution._generate_block_chunk`,
  `_audiobook_repair_call`, `finalize_audiobook_block_for_delivery`, `setup.execute_processing_run`, `late_phases` вокруг
  экспорта и писателя, `narration_document.build_narration_document_plan`, `glossary_phase._stage_usage` и её вызовы), их
  тесты; в промпте — base/head SHA, команды `git diff --stat` и `git log --oneline`, литеральные абсолютные пути, путь к
  спеке и плану, отдельным абзацем что измерено оператором (замеры `research.md` R1–R4, R8, R9, R13; WSL ему закрыт,
  данные `D:\Temp\docxai-research\073\` — читать и считать может); требовать `file:line`, частоту и чем измерена,
  уверенность, вердикт последней строкой из фиксированного набора; формулировки без «атакуй/сломай». Каждую находку
  проверить по коду и приземлить (правка с тестом / Changelog / Non-goals). Отчёт — `docs/reviews/CODEX_REVIEW_073_<YYYY-MM-DD>.md`
  с промптом и таблицей «поднято / вердикт / замерено».
- [ ] **T-Z6** После правок по ревью — снова T-Z2/T-Z3; статус спеки и `docs/WHERE_WE_ARE.md`; слияние `073/integration` в
  `main`, push.
- [ ] **T-Z7** Спека не объявляется закрытой до WP-Y (или до явного решения владельца закрыть без замера).

## WP-Y. Замер FR-012 (оркестратор, ПЛАТНО — нужно согласие владельца)

- [ ] **T-Y1** Бесплатно: проверка базы по SHA каждого базового прогона (`6379154`, `8adf780`, `cf86245` — `git_head` их
  отчётов): полный diff `src/` и входных документов до HEAD, оценка каждого коммита (`quickstart.md` §6, research R14).
  Если база устарела — [?] [$] согласие на новую базу (≈ 0,39 $).
- [ ] **T-Y2** [?] [$] Согласие владельца на сумму (≈ 0,42 $: RM гл. 3, Money гл. 3, полная Money с 073; research R13).
- [ ] **T-Y3** [$] Канонические прогоны (`quickstart.md` §6), по одному. При падении профиля — свежий run report,
  `failed_checks` дословно с `actual` / `threshold` и отношением, только потом гипотезы.
- [ ] **T-Y4** Читать по таблице `quickstart.md` §6. SC-002 — скрипт оркестратора вне git (сопоставление абзацев —
  приём `D:\Temp\docxai-research\073\baseline_forms.py`): по КАЖДОЙ принятой записи артефакта словаря — исходные вхождения
  с ID абзацев, сопоставленный абзац выхода, подтверждённые / отсутствующие / неоднозначные по правилу формы SC-002
  (слово чтения или его основа без двух последних букв, без знаков ударения и регистра); пустой словарь или 0
  проверенных — «не проверено». SC-003 — заголовки с «N.», номер виден и сквозь `**…**` (на полной Money 46, из них 10
  выделенных; синтетический `## **1. …**` — проверка самого скрипта). SC-010 — `reading_glossary_unresolved_count == 0`
  на трёх входах. 30 пар на главу — чтение; набор омографов для SC-004 составляет читающий.
- [ ] **T-Y5** [?] Владелец слушает главу в ElevenLabs (`.tts.docx`) и в Voice Studio (`.tts.minimax.txt`). Итоги — в
  Changelog спеки как есть.
