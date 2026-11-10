# Research: текст для озвучки в DOCX и PDF

**Spec**: [spec.md](spec.md) | **Plan**: [plan.md](plan.md) | **Date**: 2026-11-10

Все ссылки `file:line` сверены 2026-11-10 на `main` @ `f6de2fd` (ветка `072/integration` создана от него; код между
`2e5e8d5`, на котором писалась спека, и `f6de2fd` не менялся — менялись только `specs/` и `docs/`). Пути — относительно
`src/docxaicorrector/`, если не сказано иное. Замеры — без модели, в WSL Debian, интерпретатор `.venv/bin/python -I`
(Python 3.13.5, python-docx 1.2.0, pdfminer.six 20260107, LibreOffice 25.2.3.2); скрипты и сырые результаты — вне git:
`D:\Temp\docxai-research\072\` (`measure_pdf_export.py` → `out\results.json`, `measure_pdf_export_2.py` →
`out2\results.json`, `measure_pdf_export_3.py` → `out3\results.json`, `forecast_fr003.py` → `forecast_fr003.json`,
`probe_core_props.py`). Вход замеров PDF — `.tts.txt` прогона FR-009 спеки 070
(`D:\Temp\docxai-research\070-fr009\runs\archive\20261110T074147Z_40074_money_full_standard_translated_ru\Money_Sustainability_full_standard_translated.tts.txt`,
1 224 абзаца, 459 234 знака) — только как объём текста, заголовки синтетические (каждый 55-й абзац — `Heading 1`, 23
штуки; каждый сотый — с одиночным `\n` внутри).

Формат каждого решения: **решение → почему → отвергнутые альтернативы**.

---

## R1. Где хранится уровень заголовка (FR-002)

**Решение.** Новое поле `NarrationParagraphRecord.heading_level: int | None = None` — последним, со значением по
умолчанию (`pipeline/audiobook_pass.py:116-126`; записи в тестах строятся именованными аргументами,
`tests/test_audiobook_pass.py:610`, `tests/test_narration_markdown.py:102`, — поле по умолчанию их не ломает). Уровень
вычисляет ОДНА чистая функция `narration_heading_level(*, role: str, source_text: str) -> int | None` в том же модуле:
роль `heading` и префикс исходника `^(#{1,6})[ \t]+\S` (сегодня это тело `_with_source_heading_prefix`,
`pipeline/audiobook_pass.py:435-461`) → число `#`; иначе `None`. Вызывается один раз — в `finalize_audiobook_block`
при создании записи (`:253-264`; у входа уже есть `role` и `source_text`, `AudiobookParagraphInput`, `:130-145`).
`FinalizedAudiobookBlock` (`:148-154`) получает `heading_levels_by_id: Mapping[str, int]` рядом с `texts_by_id`;
`rebuild_block_with_narration_texts` (`:375-432`) получает его аргументом и ставит префикс `"#" * level` по нему, а не
по исходнику; `_with_source_heading_prefix` становится функцией от уровня. Вызов в
`pipeline/block_execution.py:1614-1619` передаёт `finalized.heading_levels_by_id`.

**Почему.** Источник один — правило FR-002 живёт в одной функции, обе проекции (DOCX для проверки и `.tts.docx`) читают
его результат. Вход финализатора уже несёт ровно те данные, которые читает сегодняшняя функция (`role`, исходник из
`_block_source_texts`, `:284-294` — тот же, что берёт `rebuild`, `:416`), значит поведение DOCX для проверки не
меняется: характеристический тест сравнивает старый и новый текст блока на матрице «роль × префикс × пустой текст ×
текст, начинающийся с `#`» (Non-goals: DOCX для проверки не меняется).

**Отвергнуто.**
- **Уровень в `AudiobookParagraphInput`** (вычислять при построении входа, `:312-372`). Работает, но тогда у
  неадресуемых входов (`paragraph_id == ""`, `:363-372`) тоже нужен уровень, а запись всё равно должна его нести —
  два места вместо одного.
- **Повторное чтение префикса при сборке `.tts.docx`** из задания блока. Второе правило — ровно то, что FR-002
  запрещает.
- **Уровень из `paragraph.heading_level` подготовки** (как в `D:\Temp\docxai-research\elevenlabs-studio\heading_levels.py:31`).
  Это ДРУГОЙ сигнал (Codex 8); DOCX для проверки строится по префиксу исходника задания. На корпусе они совпали
  (R11: у всех 163 заголовков полной Money префикс есть), но правило одно — префикс.

## R2. Как сборка отдаёт группы, не меняя байты `.tts.txt` (FR-001, SC-004, Anti-regression 1)

**Решение.** `pipeline/narration_postprocess.py`: новый `@dataclass(frozen=True) NarrationGroup(paragraph_ids:
tuple[str, ...], role: str, heading_level: int | None, text: str)` и поле `NarrationAssembly.groups:
tuple[NarrationGroup, ...]` (`:100-106`). `assemble_narration_records` (`:138-204`) уже строит локальные `groups` и
`group_texts` (`:154-167`); каждая группа превращается в `NarrationGroup` с ТЕМ ЖЕ `group_text`, из которого собирается
`text` (`:167`) — то есть `assembly.text == "\n\n".join(g.text for g in assembly.groups)` по построению. Роль группы —
роль первой записи; уровень — уровень первой записи, если роль `heading` (склейка соединяет только `body` + `body`,
`narration_paragraph_continues`, `:109-122`, поэтому группа-заголовок всегда из одной записи — инвариант проверяется
тестом). `_build_narration_text` (`:207-239`) по-прежнему возвращает `str` и дополнительно кладёт
`state.narration_groups = list(assembly.groups)` рядом с `narration_joined_paragraph_id_pairs` (`:221-223`); поле
объявляется в `ProcessingState` (`pipeline/contracts.py:260`, блок полей озвучки `:270-290`).

Золотой тест SC-004 пишется ПЕРВЫМ на `f6de2fd`: синтетический набор записей (роли, склейки, `\n` внутри, `#` в теле,
U+0301) → SHA-256 `assembly.text` литералом; зелёный до и после правки. Плюс существующие
`tests/test_audiobook_pass.py:630-830`, `tests/test_narration_markdown.py` — без изменений.

**Почему.** Склейки определяются один раз; TXT и DOCX — две проекции одного списка групп (FR-001). Возвращаемый тип
`_build_narration_text` не меняется: его подменяют тесты (`tests/test_late_phases_finalize_gate_persistence.py:150`,
`:873` — лямбды, возвращающие `None`).

**Отвергнуто.**
- **`_build_narration_text` возвращает пару (текст, группы).** Ломает подмены выше и вызов
  `pipeline/late_phases.py:1138`; выигрыша нет — состояние прогона уже служит каналом для итогов сборки (`:221-223`).
- **Разбор готового `.tts.txt` по `\n\n` в абзацы DOCX.** Теряет роли, уровни и ID (нужны FR-003 (в)) — запрещено FR-001.

## R3. Где правило FR-003 и счётчики FR-006: чистый модуль плана документа

**Решение.** Новый модуль `pipeline/narration_document.py` (без python-docx, без I/O, без Streamlit):
`build_narration_document_plan(groups: Sequence[NarrationGroupLike]) -> NarrationDocumentPlan`. Вход — любой объект с
полями `paragraph_ids`, `role`, `heading_level`, `text` (`Protocol`), поэтому пакет строится и тестируется параллельно с
R2 на своих тестовых группах. Алгоритм (FR-003 в редакции владельца 2026-11-10):
1. `chapter_level = min(уровни групп-заголовков с уровнем)`, `None`, если таких нет.
2. Проход по группам: группа-заголовок С уровнем открывает или продолжает серию; продолжает, если её уровень не
   глубже (`<=`) минимума уже вошедших; иначе серия закрывается и открывается новая. Любая другая группа (тело, роль
   `heading` без уровня — FR-003 (г)) закрывает серию и выходит обычным абзацем.
3. Закрытая серия → ОДИН абзац: текст — части через `". "` (если часть уже кончается на `.` — только пробел), ID —
   все ID членов по порядку, уровень — минимум; стиль `Heading 1`, если уровень == `chapter_level`, иначе `Normal`.
   Серия из ≥ 2 членов → запись `HeadingMerge(paragraph_ids, levels, style)`.
4. Счётчики FR-006 по готовым абзацам плана: `heading1_count`; главы — отрезки между `Heading 1`, абзацы до первого
   `Heading 1` — отдельная глава (без заголовков — вся книга одна глава); `max_chapter_paragraph_count` — без самого
   абзаца `Heading 1`; `max_paragraph_chars` — по всем абзацам плана, `len(text)` в символах Python; превышение —
   строго больше 500 / 400 / 5 000 → имена в `studio_limits_exceeded` (`chapters`, `chapter_paragraphs`,
   `paragraph_chars`).

**Почему.** Это вся логика спеки, которую стоит проверять отдельно от python-docx и LibreOffice; ни слова заголовка
не читается (Конституция VII: только роль и уровень). Счёт после слияний — так велит FR-006.

**Отвергнуто.**
- **Правило в рендерере DOCX.** Смешивает решение и запись файла; тест стилей потребовал бы открывать DOCX.
- **Сливать только серии, которые станут `Heading 1`.** Владелец оставил правило (б) без изменений; одно правило для
  всех серий проще проверить, а для озвучки «Часть. Название» и два коротких абзаца звучат одинаково. Цена — 8 слияний
  на полной Money (R11), из них 7 — серии подразделов (`3 → 3`, `3 → 2`, `2 → 2`), ставшие одним обычным абзацем.

## R4. Рендерер DOCX (FR-004)

**Решение.** Новый модуль `generation/narration_docx.py`: `render_narration_docx(paragraphs:
Sequence[NarrationDocumentParagraphLike], *, title: str) -> bytes`, вход — пары «стиль, текст» (тот же приём
`Protocol`, что в R3). `docx.Document()` (шаблон python-docx), стили `Normal` и `Heading 1` получают явный шрифт
`Times New Roman` во всех слотах `w:rFonts` (`ascii`, `hAnsi`, `cs`, `eastAsia`; атрибуты темы снимаются) — R5. Каждый
абзац — `document.add_paragraph(style=...)` и ОДИН `add_run(text)`: python-docx сам превращает `\n` в `<w:br/>`, и
`paragraph.text` возвращает исходную строку (замер: `run_text_newline_roundtrip = true`; на полной книге 1 224 абзаца,
из них 10 с `\n`, `paragraph_texts_equal = true`, `out2\results.json`). Разметка не разбирается: строка
`# не заголовок *звёзды* _подчёркивания_ <тег> > цитата\n— тире в начале строки` читается обратно байт в байт
(`literal_markup_roundtrip = true`). Свойства документа: `title` = основа имени исходника, `author` и `comments`
очищаются (шаблон пишет `python-docx` и `generated by python-docx`, `probe_core_props.py`). К `section.header` /
`footer` рендерер НЕ обращается: доступ к ним в python-docx создаёт часть колонтитула (замер: после чтения
`header.paragraphs` у секции появился собственный колонтитул) — тест проверяет, что в zip нет `word/header*.xml` /
`word/footer*.xml`. Сборка полной книги — 0,12–0,15 с, 250 КБ (`out2`, `out`).

Символы, недопустимые в XML (управляющие, кроме `\t`/`\n`), python-docx отвергает `ValueError` (замер:
`"a\x0bb"` → `ValueError: All strings must be XML compatible…`). Рендерер их не чистит (FR-004 — дословно): отказ
сборки DOCX → `ERROR` `audiobook_narration_docx_failed`, книга выдаётся без `.tts.docx` и `.tts.pdf` (Anti-regression 3).
Чистка озвучки (`text/narration_cleanup.py`) таких символов не порождает, исходный DOCX их не содержит (XML); остаётся
только ответ модели — принятый крайний случай.

**Почему.** python-docx — уже зависимость (`generation/_generation.py:3945` строит им reference-документ); Pandoc-путь
(`generation/_generation.py:3798-3830`, формат `markdown+raw_html+superscript+subscript`) интерпретирует `*`, `_`,
`#`, `<…>` — нарушение FR-004 (Codex, «Какой путь сборки реалистичен»). Слой `generation/` — там, где строятся
выходные документы; модуль не знает о конвейере.

**Отвергнуто.**
- **Pandoc с экранированием.** Экранирование Markdown — второй парсер, который надо доказывать; python-docx пишет
  строку как есть.
- **Reference-документ проекта** (`_build_reference_docx`). Несёт нумерацию и оформление DOCX для проверки, которые
  Studio не нужны; минимальный шаблон проще проверить на «нет колонтитулов, нет оглавления».
- **Шрифт из `[output.fonts]`** (`tests/test_config.py:1287-1330`). Это настройка вида DOCX для проверки; `.tts.docx`
  нужен гарантированно кириллический шрифт, одинаковый в Word и в LibreOffice (R5). Ручной ручки нет (владелец: полная
  автоматизация).

## R5. Шрифты (FR-005: «шрифт с кириллицей встроен»)

**Замер** (`out\results.json` → `fonts`):
- `fc-list :lang=ru family` — 26 семейств с кириллицей: C059, Carlito, DejaVu Sans/Serif/Mono, Liberation
  Mono/Sans/Sans Narrow/Serif, Linux Biolinum/Libertine, Nimbus Mono/Roman/Sans, Noto Mono/Sans/Serif (и Display/Mono),
  P052, URW Bookman/Gothic, Z003.
- `fc-match`: `Times New Roman` → Liberation Serif; `Arial` → Liberation Sans; `Calibri` → Carlito; `Cambria` → Caladea
  (кириллицы в Caladea нет — её нет в `fc-list :lang=ru`); `serif` → Noto Serif.
- Пакеты: `fonts-liberation 1:2.1.5-3`, `fonts-crosextra-carlito`, `fonts-crosextra-caladea`, `fonts-dejavu*`,
  `fonts-noto-core`, `fonts-urw-base35` и др.; `fonts-liberation` — только **Recommends** у `libreoffice` (`apt-cache
  depends`), в `system-requirements.apt` (`:1-8`) пакета шрифтов нет; `scripts/setup-wsl.sh:65-78` проверяет лишь
  запуск `soffice`.
- **Документ с шаблоном python-docx без явного шрифта:** PDF встроил `Caladea-Regular` (тело, латиница),
  `NotoSerif-Regular`/`-Bold` (кириллица тела — подмена, Caladea её не имеет) и `Carlito-Bold` (заголовки) — четыре
  шрифта, смешанный набор. **С явным `Times New Roman`:** ровно `LiberationSerif` и `LiberationSerif-Bold`, оба
  встроены подмножеством TrueType (`out2\results.json` → `full_checks.fonts_embedded`).

**Решение.** Явный `Times New Roman` в стилях `.tts.docx` (R4): в Word на Windows — родной шрифт, в LibreOffice —
метрически совместимый Liberation Serif с кириллицей. `system-requirements.apt` получает строку `fonts-liberation`,
`scripts/setup-wsl.sh` (`verify_runtime`) — проверку `fc-list ":lang=ru:family=Liberation Serif"` непуста. Гард
`tests/test_script_contract_static.py:168-188` проверяет наличие `libreoffice`/`pandoc`/`antiword` в файле — строка
шрифтов его не задевает.

**Отвергнуто.** `Calibri` (→ Carlito, кириллица есть) — работает так же; Times New Roman выбран как привычный шрифт
книжного текста. Встраивание шрифта в сам DOCX — Word на Windows шрифт имеет, Studio шрифт не читает.

## R6. PDF: синтаксис фильтра, закладки, встраивание, проверка текста (FR-005, SC-003)

**Замер** (`out\results.json` → `filters_small`, 120 абзацев, 3 `Heading 1`):

| `--convert-to` | код | закладок | уровни | шрифты встроены |
|---|---|---|---|---|
| `pdf` | 0 | 3 | {1} | да |
| `pdf:writer_pdf_Export:{"ExportBookmarks":{"type":"boolean","value":"true"}}` | 0 | 3 | {1} | да |
| `pdf:writer_pdf_Export:{"ExportBookmarks":{"type":"boolean","value":"false"}}` | 0 | **0** | — | да |
| то же + `"EmbedStandardFonts":{"type":"boolean","value":"true"}` | 0 | 3 | {1} | да |

JSON-синтаксис параметров фильтра LibreOffice 25.2.3.2 принимает (отключение закладок действительно их убирает —
значит, параметр читается, а не игнорируется). На полной книге: 23 закладки уровня 1, заголовки закладок совпадают с
текстами `Heading 1` по порядку (`outline_titles_equal_h1_nows = true`), 191 страница, 884 КБ.

**Решение.** Фильтр — явно `pdf:writer_pdf_Export:{"ExportBookmarks":{"type":"boolean","value":"true"}}` (по умолчанию
закладки тоже есть, но явный параметр защищает от смены умолчания и от чужого профиля). Команда:
`soffice -env:UserInstallation=<file-URI каталога профиля> --headless --norestore --convert-to <фильтр> --outdir <tmp>
<tmp>/<stem>.tts.docx`. `EmbedStandardFonts` не нужен — шрифты встроены и без него.

**Проверка текста (SC-003).** Сравнение «схлопнуть пробелы в один» НЕ работает: pdfminer `extract_text` вставляет
лишние пробелы внутри строк (полная книга: 468 676 знаков против 458 011 ожидаемых; первое расхождение — пробел перед
точкой, `вэ вэ .`). Сравнение после удаления ВСЕХ пробельных символов с обеих сторон: на наборе из 120 абзацев —
равенство (20 420 = 20 420), каждый абзац находится по порядку, хвоста нет; отрицательные контроли (выпавший абзац,
лишний дубль) расходятся (`negative_drop_detected`, `negative_dup_detected` = `true`). Буквы, пунктуация и повторы при
этом сохраняются — это и есть «нормализация пробелов и переносов» SC-003. Извлечение полной книги pdfminer — 9,5 с,
поэтому тест SC-003 берёт короткий синтетический набор.

**Комбинирующий знак U+0301** — предел, а не дефект кода. В полной книге он один (`временны́е`); pdfminer вернул на его
месте `-` (`out2\results.json` → `full_checks.pdf_ctx`: `временны-ерамки`), единственное расхождение на 398 717
знаках. В пробе со знаком (`out3\stress.tts.pdf`) — `ы́(cid:14)`: U+0301 через ToUnicode и лишний глиф без отображения.
Заглавные гласные (`замОк`) и `ё` извлекаются верно. Владелец работает с DOCX, где знак побайтно сохранён (SC-001);
спека записывает это в Non-goals, набор SC-003 — без комбинирующих знаков.

## R7. Время, тайм-аут и параллельные экспорты (FR-005, SC-005, SC-006)

**Замер** (секунды, `.venv/bin/python` → `soffice`, процесс в своей группе):

| Что | Где файлы | Замеры |
|---|---|---|
| полная книга (1 224 абзаца, 191 стр.), НОВЫЙ профиль на конвертацию | `/mnt/d` (9p) | 8,35 / 8,39 / 8,26 |
| то же | `/tmp` | 7,07 / 7,06 / 7,03 / 7,04 / 7,05 |
| полная книга, профиль ПЕРЕИСПОЛЬЗОВАН (прогрет) | `/tmp` | 0,90 / 0,88 / 0,90 (`/mnt/d`: 2,26 / 2,29) |
| 120 абзацев, новый профиль | `/tmp` | 6,53 / 6,41 / 6,46 |
| две полные книги ОДНОВРЕМЕННО, у каждой свой новый профиль | `/tmp` | по 2,14 / 2,10 / 2,09 с, стена 2,1 с (3 пары) |
| две конвертации одновременно с ОДНИМ общим профилем | `/tmp` | **5 из 10 не дали PDF** (в каждой из 5 пар один процесс кончился кодом 1 за ~1,5 с, без вывода) |
| новый профиль: главный поток / stdin=`/dev/null` / рабочий поток | `/tmp` | 6,5–6,6 во всех трёх вариантах |

Почти всё время одиночной конвертации — создание профиля (≈ 6 с при 0,9 с на сам экспорт). Почему пара параллельных
процессов с новыми профилями укладывается в 2,1 с, а одиночный — в 7 с, замер не объяснил (поток, stdin и файловая
система исключены); на выбор тайм-аута это не влияет. Процессов `soffice` после замеров не осталось (`pgrep -c` = 0);
профиль — ≈ 2–3 МБ во временном каталоге, удаляется вместе с ним.

**Решение.**
- **Тайм-аут — 60 с** (`NARRATION_PDF_TIMEOUT_SECONDS`): в 7 раз больше худшего замера полной книги (8,4 с на `/mnt/d`);
  книга втрое длиннее при линейном росте экспорта (0,9 с) укладывается с запасом. 120 с импорта
  (`processing/processing_runtime.py:83`) не берётся: зависание экспорта задерживает уже готовый результат, и минута —
  верхняя граница этой задержки. По тайм-ауту группа процессов завершается (`_terminate_process_tree`, `:390-410`).
- **Профиль — новый на каждую конвертацию**, каталог `<tmp>/lo_profile` внутри того же `tempfile.TemporaryDirectory`, что
  вход и выход: удаляется вместе с ним. Общий профиль ломает параллельные конвертации (замер выше) — SC-006 и
  Anti-regression 7. 6 с за изоляцию приемлемы: экспорт идёт в фоновом процессе после сборки книги.
- **Импорт PDF/DOC не меняется** — его вызовы `soffice` (`:413-450`, `:453-489`) по-прежнему без отдельного профиля. Замер
  показывает, что два одновременных импорта с общим профилем тоже рискуют (одна из двух конвертаций падает), но это
  вне объёма 072 (Конституция VI) — вынесено в «Что не определено» плана как находка для отдельной спеки.

## R8. Один поиск `soffice` и общий помощник процесса (FR-005)

**Решение.** Новый модуль `runtime/external_process.py` (слой `runtime/` — ниже `pipeline/`, `generation/` и
`processing/`): `find_soffice_binary() -> str | None` (`shutil.which("soffice") or shutil.which("libreoffice")`),
`run_completed_process(...)` и `terminate_process_tree(...)` — перенесены дословно из
`processing/processing_runtime.py:321-387` и `:390-410`. В `processing_runtime` три копии поиска (`:454`, `:1244`,
`:1282`) заменяются вызовом `find_soffice_binary()`; имена `_run_completed_process` и `_terminate_process_tree`
остаются импортированными псевдонимами (их подменяют тесты: `tests/test_processing_runtime.py:1404-1450`, `:1491-1499`,
`:1608-1616`, `:1734-1758`, `:2252-2258`); `shutil.which` тесты подменяют на модуле `shutil`
(`tests/test_processing_runtime.py:2242`, `:2282`) — это действует и на новый модуль. Единственный тест, который
подменяет `_terminate_process_tree` и ждёт, что его вызовет `_run_completed_process` (`:1414-1450`), переводится на
подмену в `runtime.external_process`. Гард: `processing_runtime._run_completed_process is
external_process.run_completed_process`.

Экспорт — новый модуль `generation/narration_pdf.py`: `export_narration_pdf(docx_bytes: bytes, *, stem: str,
timeout_seconds: int = NARRATION_PDF_TIMEOUT_SECONDS, runner=run_completed_process, find_soffice=find_soffice_binary)
-> NarrationPdfOutcome`. Никогда не бросает (кроме `BaseException`): каждый отказ — `NarrationPdfOutcome(pdf_bytes=None,
reason=…)` из закрытого словаря (`data-model.md` §4). `runner` и `find_soffice` — шов для тестов CI (R14).

**Почему.** FR-005 требует один общий поиск и существующий помощник с тайм-аутом и завершением группы. Импортировать
`processing_runtime` из `pipeline`/`generation` нельзя по слоям (`processing` вызывает `pipeline`), а копия помощника
— третья копия того же. Перенос вниз — единственный вариант без дубля.

**Отвергнуто.**
- **Экспорт в `processing/`, внедрение в конвейер через `ProcessingDependencies`** (как `write_ui_result_artifacts`,
  `pipeline/contracts.py:210`). Добавляет поле контракта зависимостей и его проводку в трёх точках `_pipeline.py`
  (`:261-285`, `:404-460`, `:1010-1062`) ради одной функции; шов для тестов даёт и параметр `runner`.
- **Оставить помощник в `processing_runtime` и импортировать его оттуда** — нарушение слоёв (сегодня единственный
  обратный импорт — `pipeline/quality_gate.py:52`, повод не множить).

## R9. Где в позднем этапе строятся DOCX и PDF; Stop; отказы (FR-005, FR-006, FR-007, Anti-regression 3)

**Решение.** Новый модуль-оркестратор `pipeline/narration_exports.py`: `build_narration_exports(*, groups, source_name,
log_event, export_pdf=export_narration_pdf) -> NarrationExports` (план R3 → DOCX R4 → PDF R8; DOCX не собран → PDF не
пробуется, причина `docx_not_built`). Вызов — в `pipeline/late_phases.py` после проверки текста озвучки
(`:1273-1298`) и до границы `_stop_at_late_boundary` перед публикацией (`:1369`), только когда `narration_text is not
None` и операция `audiobook`. Перед вызовом — новая граница `_stop_at_late_boundary("Обработка остановлена перед
сборкой DOCX и PDF озвучки.")` (`:624-635`): Stop до экспорта завершает прогон как остановленный — так же, как
соседние границы (`:1134`, `:1369`); во время самой конвертации Stop не опрашивается (спека FR-005: «Stop проверяется
перед запуском»; ожидание ограничено 60 с).

Результат идёт в три места: `emit_state(..., latest_narration_exports=...)` вместе с `latest_narration_text`
(`:1372-1391`); аргументы писателя группы `narration_docx_bytes`/`narration_pdf_bytes` (`:1411-1434`); поля
`ui_audiobook_artifact_saved` (`:1544-1565`, `contracts/events.md`). Notices: превышение лимитов Studio — `warning`
`result.audiobook_studio_limits_exceeded`; отсутствие PDF и DOCX показывает экран по причине из bundle (R10), не
notice. Событие `audiobook_narration_docx_failed` (ERROR), `audiobook_narration_pdf_unavailable` (WARNING),
`audiobook_studio_limits_exceeded` (WARNING) — имена с префиксом `audiobook_`, их видит сканер гарда
`tests/test_real_document_pipeline_validation.py:7948-7959`.

**Почему.** До `emit_state` — иначе байты не попадут в состояние вместе с текстом (публикация в UI происходит на
`:1373`, запись группы — позже, `:1434`). В фоновом процессе — поздний этап и так исполняется в рабочем потоке
(`processing/processing_service.py:291`), Streamlit не ждёт.

**Отвергнуто.**
- **Строить в `write_ui_result_artifacts`.** Тогда байты не дойдут до экрана (запись после `emit_state`), а писатель
  группы начнёт запускать LibreOffice.
- **Второй `emit_state` после записи группы.** Окно, когда экран показывает текст без DOCX; и лишний источник
  «старых файлов» (SC-007).
- **Stop → «PDF не собран, причина stopped», доставка продолжается.** Отличается от всех соседних границ позднего
  этапа; Stop означает «остановить прогон».

## R10. Доставка до экрана: ключ состояния, bundle, экран (FR-008, FR-009, SC-007)

**Решение.** ОДИН новый ключ состояния `latest_narration_exports` (словарь `data-model.md` §5) в
`_ALLOWED_SET_STATE_EVENT_KEYS` (`processing/processing_runtime.py:164-180`; неизвестные ключи отбрасываются с WARNING
`state_event_unknown_keys`, `:1850-1859`). Очистка: `init_session_state` (`runtime/state.py:602-615`, `setdefault`),
`reset_run_state` (`:658`, присваивание рядом с `latest_narration_text`, `:737`) — он вызывается в начале каждого
запуска (`processing/processing_runtime.py:2095`, `:2203`); аварийный обработчик рабочего потока
(`processing/processing_service.py:375-381`) обнуляет его вместе с `latest_narration_text`. **Правило пары:**
`get_current_result_bundle` (`processing/processing_runtime.py:1778-1842`) кладёт `narration_exports` в bundle только
если `latest_narration_text is not None`; поэтому все 12 мест конвейера, где сегодня обнуляется
`latest_narration_text` (`pipeline/late_phases.py:304`, `:383`, `:499`, `:776`, `:1044`, `:1166`;
`pipeline/terminal_results.py:120`; `pipeline/setup.py:485`, `:593`; `pipeline/reader_cleanup_rebuild.py:159`;
`pipeline/reader_cleanup_postprocess.py:759`; `pipeline/block_execution.py:2654`), гасят и экспорт, без правки каждого.
`build_result_bundle` (`:1689-1736`) получает `narration_exports: Mapping | None = None` и нормализует его
(неизвестные ключи отброшены, байты — `bytes` или `None`). Экран (`ui/_app.py:895-920` → `ui/_ui.py:1078`) читает
`result.get("narration_exports")`: `None` (старый bundle) → экран аудиокниги показывает TXT, Markdown и DOCX для
проверки, как сейчас.

Экран аудиокниги (`ui/_ui.py:1195-1236` переписывается для ветви `audiobook`; ветвь перевода/редактуры `:1239-1264`
не трогается): подпись «Текст для озвучки» и `st.columns(n)` из собранных форматов в порядке DOCX (`type` основной),
PDF, TXT; под ней — строка причины, если PDF или DOCX нет; подпись «Для проверки» и `st.columns(2)`: DOCX для проверки,
Markdown. Все кнопки — `width="stretch"`, `on_click="ignore"` (как сейчас). Имена: `<stem>.tts.docx`, `<stem>.tts.pdf`,
`<stem>.tts.txt` (новые `_build_narration_docx_filename`, `_build_narration_pdf_filename` рядом с
`_build_narration_filename`, `ui/_ui.py:92-93`). MIME: `application/vnd.openxmlformats-officedocument.wordprocessingml.document`,
`application/pdf`, `text/plain`. Заблокированная выдача (`blocked`) — все кнопки вторичные, как сейчас (`:1186-1194`).

**Почему.** Один ключ — один атомарный набор: экран не может показать DOCX одного прогона и PDF другого; одна строка
в списке разрешённых ключей, одна в сбросе. Правило пары вместо 12 правок — те места принадлежат чужим этапам, а
байты экспорта появляются только вместе с доставленным текстом (`late_phases.py:1373`).

**Отвергнуто.**
- **Три ключа** (`latest_narration_docx_bytes`, `…_pdf_bytes`, `…_pdf_reason`) — три строки списка, три сброса и
  возможность рассинхронизации.
- **Читать файлы из `.run/ui_results/`** — экран строится из состояния сессии, истории результатов нет (Non-goals).
- **Notice об отсутствии PDF** вместо строки у кнопок — сообщение оказалось бы выше, в общем списке, далеко от места,
  где пользователь ищет кнопку; причина и так живёт в bundle.

## R11. Прогноз FR-003 / FR-006 на корпусе без модели (SC-002, FR-011)

**Замер** (`forecast_fr003.py` → `forecast_fr003.json`): правило FR-003 в редакции владельца применено к ПОДГОТОВКЕ
трёх переведённых входов (`tests/sources/translated/*.docx`, операция `audiobook`, без клиента модели), уровень — по
префиксу исходника задания (как FR-002), исключения — причины спеки 070, склейки — правило
`narration_paragraph_continues` на исходном тексте. Тексты — исходные, поэтому длины — прогноз.

| Вход | озвучиваемых | уровни заголовков | `Heading 1` | слияний (узоры) | заголовков → обычный абзац | макс. абзацев в главе | до 1-го H1 | макс. длина абзаца |
|---|---|---|---|---|---|---|---|---|
| RM гл. 3 | 102 | {1: 1, 2: 1, 3: 7} | **1** | 1 (`2→1`) | 7 | 100 | 0 | 1 570 |
| Money гл. 3 | 96 | {1: 2, 2: 5, 3: 2} | **1** | 2 (`1→1`, `3→2`) | 6 | 93 | 0 | 2 427 |
| Money полная | 1 224 | {1: 23, 2: 70, 3: 70} | **23** | 8 (`3→3` ×3, `3→2` ×3, `3→1`, `2→2`) | 132 | 183 | 0 | 4 036 |

Роль `heading` без префикса — 0 на всех трёх (FR-003 (г) на корпусе не срабатывает). Лимиты Studio не превышены ни на
одном входе. Одно слияние `3→1` на полной Money — подраздел, чьё содержимое исключено, перед названием главы:
принятый крайний случай спеки (Non-goals, «слияние через пустой раздел»). Длины первых восьми `Heading 1` полной Money —
33, 8, 9, 10, 8, 44, 44, 57 знаков: часть глав называется коротким номером, а название (уровень 2) уходит в обычный
абзац сразу за ним (`1 → 2` не сливается по правилу (б)); глава в Studio будет названа номером — текст названия
звучит. Отмечено как наблюдение для FR-011, не как дефект: правило (б) владелец оставил.

**Вывод для FR-011:** ожидаемое число глав Studio = 23 (≥ 2 — условие FR-011 выполнимо); старое «≈ 23 серии, из них
≈ 5 — строки оглавления» спеки было прогнозом по `heading_level` подготовки — новый прогноз по префиксу даёт те же 23,
строк нераспознанного оглавления среди `Heading 1` этот замер не различает (их читает владелец на FR-011).

## R12. Группа результата и хранение (FR-007)

**Решение.** `write_ui_result_artifacts` (`runtime/artifacts.py:363-446`) получает `narration_docx_bytes: bytes | None =
None`, `narration_pdf_bytes: bytes | None = None`; пути `<stem>.tts.docx` и `<stem>.tts.pdf` (`stem` уже кончается на
`.result`, `:163-168`) добавляются в `group_entries` (`:410-433`) только если байты непусты; ключи результата
`tts_docx_path`, `tts_pdf_path` (`:438-446`). Публикация — тот же `_atomic_write_group` (`:192-232`): сбой записи
любого члена откатывает группу целиком — та же гарантия, что у `.tts.txt` сегодня. Протокол писателя
`ResultArtifactWriter` (`pipeline/contracts.py:151-165`) получает те же два аргумента. Суффиксы хранения
`_UI_RESULT_GROUP_SUFFIXES` (`runtime/artifact_retention.py:90-97`) — `.result.tts.docx` и `.result.tts.pdf` (перед
`.result.docx`, чтобы порядок читался как «длинный суффикс раньше»; пересечения нет: `x.result.tts.docx` не кончается
на `.result.docx`).

**Почему суффиксы обязательны, а не «для порядка».** Файл без известного суффикса уходит в `passthrough_paths`
(`runtime/artifact_retention.py:206-209`), и этот список дальше не читается — такой файл НИКОГДА не удаляется ни по
возрасту, ни по числу групп. Без суффиксов каждый прогон аудиокниги оставлял бы в `.run/ui_results/` два вечных
файла. Тест хранения проверяет удаление обоих вместе с группой.

**Отвергнуто.** Отдельная запись DOCX/PDF после группы — нарушает FR-007 («тем же `_atomic_write_group`») и даёт
группу, в которой событие называет файл, которого нет.

## R13. Раннер реальных документов (FR-007, FR-011)

**Решение.** `tests/artifacts/real_document_pipeline/run_lietaer_validation.py`: из состояния прогона
(`state.get("latest_narration_exports")` рядом с `latest_narration_text`, `:6360`) байты пишутся в каталог прогона как
`<output_basename>.tts.docx` / `.tts.pdf` (рядом с `.tts.txt`, `:6386-6414`); `output_artifacts` получает
`tts_docx_path`, `tts_pdf_path`, `latest_tts_docx_path`, `latest_tts_pdf_path` (`:6519-6540`); копия в `latest`-псевдонимы
и манифест — `_write_latest_aliases` (`:1595-1632`); строки сводки `tts_docx_path=…`, `tts_pdf_path=…` рядом с
`tts_text_path` (`:6798`). Счётчики — только из события: `_NARRATION_SUMMARY_FIELDS` (`:5011-5028`) получает
`heading1_count`, `heading_merge_count`, `demoted_heading_count`, `studio_max_chapter_paragraph_count`,
`studio_max_paragraph_chars`, `narration_pdf_status`, `narration_docx_status`; `_NARRATION_SUMMARY_JSON_FIELDS`
(`:5029-5039`) — `heading_merges`, `heading_levels_present`, `studio_limits_exceeded`, `narration_pdf_unavailable_reason`.
Второго канала вычисления нет (как у спеки 054/070, `_extract_narration_artifact_record`, `:5052-5072`).

Для FR-011 раннер дополнительно открывает `.tts.docx` (python-docx, как `.docx` на `:6395-6409`) и пишет в отчёт
`tts_docx_openable`, `tts_docx_paragraphs`, `tts_docx_heading1_count`, `tts_docx_other_heading_style_count` (должно быть
0, SC-002) — это проверка файла, не второй счёт плана.

## R14. Как проверяется SC-003 и чем CI заменяет конвертер

**Решение.**
- `tests/test_spec_072_narration_pdf_system.py` — `pytestmark = pytest.mark.system_deps` (маркер объявлен,
  `pyproject.toml:55`; CI и `scripts/docker-ci-parity.sh` его исключают, `.github/workflows/ci.yml:92`,
  `scripts/docker-ci-parity.sh:42`). Без `soffice` — `pytest.skip`, но если задано
  `DOCXAI_REQUIRE_REAL_DOCUMENT_CAPABILITIES` — падение (образец: `tests/test_real_document_validation_corpus.py:37-39`).
  Проверяет на синтетическом наборе (≈ 60 абзацев, 3 `Heading 1`, без U+0301): текст pdfminer без пробельных символов
  равен ожидаемому, каждый абзац по порядку, хвоста нет, набор непуст; закладки уровня 1 = тексты `Heading 1`; все
  шрифты встроены (`FontFile*` у дескриптора); отрицательные контроли — выпавший абзац и дубль не проходят ту же
  функцию сравнения; SC-006 — два `export_narration_pdf` в потоках дают два PDF, оба проходят проверку; после — во
  временном каталоге нет `lo_profile`, `pgrep -c soffice` не вырос.
- `tests/test_spec_072_narration_pdf.py` — без системных зависимостей, в CI: подменённые `runner`/`find_soffice`.
  Проверяет команду (`-env:UserInstallation=file://…/lo_profile`, `--headless`, `--norestore`, точная строка фильтра,
  `--outdir`, вход `<stem>.tts.docx`), `cleanup_process_group=True`, `timeout_seconds=60`; уникальность каталога профиля у
  двух вызовов; удаление временного каталога; причины: `soffice_not_found` (finder → `None`), `timeout`/`failed`
  (`runner` бросает `RuntimeError` с текстом о времени / без), `missing_output` (runner ничего не пишет), `empty_output`
  (пишет 0 байт), `not_pdf` (пишет не `%PDF-`). Сбой → `pdf_bytes is None`, исключение не выходит.
- Интеграционный тест позднего этапа (WP-H) подменяет `export_narration_pdf` на модуле `pipeline.narration_exports` —
  SC-005 без LibreOffice: прогон успешен, `.tts.txt` и `.tts.docx` есть, причина — в событии и в bundle.

**Почему.** Реальный LibreOffice есть только в WSL; CI его не ставит (Codex 7). Подмена конвертера проверяет весь
контракт вокруг него, системный тест — сам PDF. Pdfminer в `.venv` есть (`pdfminer.six 20260107`).

**Отвергнуто.** Ставить LibreOffice в CI — сотни мегабайт и минуты на каждый прогон ради трёх тестов; решение о CI
принадлежит владельцу и не нужно для 072.

## R15. Владение `docs/testing/TEST_TIER_INVENTORY.md`

**Решение.** Гард `tests/test_script_contract_static.py:363-397` требует, чтобы список совпадал с файлами `tests/test_*.py`
ровно — строку нельзя внести заранее, а внесённая пакетом строка пересекается с соседним пакетом. Поэтому файл
принадлежит ОРКЕСТРАТОРУ: при слиянии каждого пакета он добавляет строки его новых тестов (перечислены в `tasks.md` у
пакета; `## Unit-Contract`, системный — `## System-Deps`). В боковом worktree пакета гард инвентаря красный до слияния —
ожидаемо, пакет его не запускает.
