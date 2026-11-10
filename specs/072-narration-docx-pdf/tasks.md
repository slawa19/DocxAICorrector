# Tasks: текст для озвучки в DOCX и PDF

**Spec**: [spec.md](spec.md) | **Plan**: [plan.md](plan.md) (раздел «Порядок реализации: пакеты работ») |
**Контракты**: [contracts/](contracts/) | **Данные**: [data-model.md](data-model.md), [research.md](research.md) |
**Проверка**: [quickstart.md](quickstart.md)

Tier: полный цикл (Конституция, принцип III). Задачи сгруппированы по пакетам WP-A…WP-I; порядок внутри пакета всегда
один: (A) характеристические / золотые тесты того, что НЕ должно измениться → (B) падающие тесты нового поведения
(анти-вакуум: у каждого сказано, чем доказано, что он падает без правки) → (C) реализация → (D) каноническая проверка
пакета. Пакет владеет ТОЛЬКО перечисленными у него файлами (Конституция VI); правка вне перечня запрещена — нужда в
ней возвращается оркестратору вопросом.

## Формат и общие правила

- `T-<пакет><номер>`; `[P]` — можно параллельно с соседними задачами того же пакета (разные файлы, нет зависимости);
  `[?]` — решение оркестратора/владельца, агент не гадает; `[$]` — платно, только с согласия владельца. Между пакетами
  параллельность задана волнами.
- **База**: `072/integration` от `main` @ `f6de2fd`. Ссылки `file:line` плана сверены там; если ветка ушла вперёд —
  сверить заново (Конституция VIII), расхождение — вопрос оркестратору.
- **Каноническая проверка пакета** — одна команда на один selector, selector ДО опций pytest:
  `wsl.exe -d Debian --cd "D:\Temp\claude\wt-072-<slug>" -- bash scripts/test.sh <selector> -q` (`.venv` — симлинк на
  главное дерево). Из Git Bash `$VAR` на границе `wsl.exe` схлопывается — только литеральные пути, без циклов `for`.
  Голый `python` / `.venv-win` / `py -m pytest` запрещены (debug-путь — только с пометкой `debug-only`). Оборванный
  вывод — сначала проблема транспорта; сужать до node selector.
- **Тесты истории** в боковом worktree пропускаются; проверяются в главном дереве (T-Z3). `git` в боковом worktree под
  WSL не работает — коммиты и `git diff --check` из Git Bash в worktree.
- **Конституция VII**: ни в коде, ни в тестах нет текста книг и литералов корпуса; примеры — вымышленные, той же ФОРМЫ;
  правила — по роли и уровню, не по словам.
- **Новый тестовый файл** — строку в `docs/testing/TEST_TIER_INVENTORY.md` добавляет ОРКЕСТРАТОР при слиянии пакета
  (research R15); в worktree пакета гард инвентаря (`tests/test_script_contract_static.py::test_inventory_lists_every_top_level_test_file_exactly_once`)
  красный — пакет его не запускает.
- **LF** во всех новых файлах; после правок `git diff --check`. Полные тексты в лог не пишутся.
- Тема коммита пакета: `spec 072: <что сделано>`.

## Волны и зависимости

```text
T-01 (оркестратор): worktrees от 072/integration
волна 1 (параллельно):  WP-A  WP-B  WP-C  WP-D  WP-E  WP-G       слияние: любой порядок, полный прогон после каждого
волна 2:                WP-F  ← D
волна 3:                WP-H  ← A, B, C, D, E, F
волна 4:                WP-I  ← H
приёмка:                T-Z1…T-Z7 → WP-Y (платно, по согласию владельца)
```

Критический путь: **WP-D → WP-F → WP-H → WP-I**.

## Подготовка (оркестратор)

- [ ] **T-01** Worktrees от `072/integration`: `D:\Temp\claude\wt-072-{groups,document,docx,pdf,group,screen}` для волны 1
  (ветки `072/wp-a-groups`, `072/wp-b-document`, `072/wp-c-docx`, `072/wp-d-pdf`, `072/wp-e-result-group`,
  `072/wp-g-screen`), симлинк `.venv` на главное дерево.
- [ ] **T-02** При первом слиянии кода — статус спеки `IN PROGRESS` и абзац спеки 072 в `docs/WHERE_WE_ARE.md` (иначе
  `test_spec_status_consistency` / `test_where_we_are_freshness` красны в главном дереве).

---

## WP-A. Записи и группы (FR-001, FR-002)

**Ветка**: `072/wp-a-groups` | **Worktree**: `D:\Temp\claude\wt-072-groups` | **Агент**: Sonnet / high |
**Сначала слиты**: ничего | **Владеет**: `src/docxaicorrector/pipeline/audiobook_pass.py`,
`src/docxaicorrector/pipeline/block_execution.py` (только `finalize_audiobook_block_for_delivery`, `:1572-1619`),
`src/docxaicorrector/pipeline/narration_postprocess.py`, `src/docxaicorrector/pipeline/contracts.py` (только поле
`ProcessingState.narration_groups` и два аргумента `ResultArtifactWriter`, `:151-165`),
`tests/test_spec_072_narration_groups.py` (нов.). Решения — research R1, R2; сущности — `data-model.md` §1–2.

**A. Характеристика (ДО любой правки, зелёные на `f6de2fd`)**
- [ ] **T-A1** Золотой `.tts.txt` (SC-004): синтетические `NarrationParagraphRecord` — заголовок, проза, склейка
  `body`+`body` (первый без точки, второй со строчной), одиночный `\n` внутри, абзац тела, начинающийся с `#`, U+0301 и
  заглавная гласная, `needs_review` (`source_restored`, `source_fallback`) → `assemble_narration_records(...).text`;
  SHA-256 вписать литералом, полученным ОДИН раз каноническим путём на `f6de2fd`.
- [ ] **T-A2** Текст блока DOCX для проверки: `rebuild_block_with_narration_texts` на матрице «роль `heading`/`body` ×
  исходник с префиксом `#`/`##`/`###`/без × текст озвучки пустой / обычный / начинающийся с `#`» — снимок результата
  (тексты и статусы `ParagraphDisposition`) литералом.

**B. Падающие тесты** (`tests/test_spec_072_narration_groups.py`)
- [ ] **T-A3** `narration_heading_level(role="heading", source_text="## Глава")` → 2; `role="body"` с `## …` → `None`;
  `heading` без префикса → `None`; `#######` (7) → `None` (падает: функции нет).
- [ ] **T-A4** `finalize_audiobook_block` кладёт `heading_level` в запись и `heading_levels_by_id` в результат (падает:
  поля нет); неадресуемый вход — `None`.
- [ ] **T-A5** `assemble_narration_records(...).groups`: `text == "\n\n".join(g.text …)`; ID групп по порядку с
  кратностью = ID записей; склеенная группа несёт оба ID; группа `heading` — одна запись и её уровень; группа тела —
  `heading_level is None` (падает: `groups` нет).
- [ ] **T-A6** `_build_narration_text` на двойнике состояния пишет `state.narration_groups` (те же группы) и
  возвращает прежний текст (падает).

**C. Реализация**
- [ ] **T-A7** `pipeline/audiobook_pass.py`: `narration_heading_level`, поле записи, `heading_levels_by_id`,
  `rebuild_block_with_narration_texts(..., heading_levels_by_id=…)`, `_with_source_heading_prefix` от уровня.
- [ ] **T-A8** `pipeline/block_execution.py:1614-1619`: передать `finalized.heading_levels_by_id`.
- [ ] **T-A9** `pipeline/narration_postprocess.py`: `NarrationGroup`, `NarrationAssembly.groups`, запись в состояние;
  `pipeline/contracts.py`: `ProcessingState.narration_groups: list[Any] = field(default_factory=list)`,
  `ResultArtifactWriter` + `narration_docx_bytes`, `narration_pdf_bytes` (`bytes | None = None`).

**D. Проверка**
- [ ] **T-A10** Отдельными командами: `tests/test_spec_072_narration_groups.py`, `tests/test_audiobook_pass.py`,
  `tests/test_narration_markdown.py`, `tests/test_narration_exclusion_addresses.py`,
  `tests/test_spec_059_translation_completeness.py`, `tests/test_spec_063_apparatus_policy.py`,
  `tests/test_document_pipeline.py`. Done: зелёные; T-A1/T-A2 не правились.

---

## WP-B. План документа (FR-003, FR-006)

**Ветка**: `072/wp-b-document` | **Worktree**: `D:\Temp\claude\wt-072-document` | **Агент**: **Opus** / high |
**Сначала слиты**: ничего | **Владеет**: `src/docxaicorrector/pipeline/narration_document.py` (нов.),
`tests/test_spec_072_narration_document.py` (нов.). Решение — research R3; сущности и таблица примеров — `data-model.md` §3.
Вход — `NarrationGroupLike` (Protocol), тесты строят свои группы; от WP-A не зависит.

**B. Падающие тесты** (модуля нет — все падают)
- [ ] **T-B1** Таблица примеров `data-model.md` §3 — каждая строка отдельным параметризованным случаем: стили, тексты
  (части через `". "`, без двойной точки), ID абзацев плана, записи `HeadingMerge` (`paragraph_ids`, `levels`, `style`).
- [ ] **T-B2** Анти-вакуум (VII): группа `body`, текст которой начинается с `#` или похож на заголовок («Глава 1»,
  короткий, заглавными) → `Normal`; ни один абзац плана не `Heading 1`, если в нём нет группы-заголовка ранга 1;
  текст понижённого заголовка присутствует в плане побайтно; сумма ID плана = ID групп по порядку с кратностью.
- [ ] **T-B3** Ни одного стиля, кроме `Heading 1` и `Normal`, при любых уровнях 1…6 (параметризация по наборам уровней).
- [ ] **T-B4** FR-006: `heading1_count`; глава до первого H1 считается; книга без заголовков — одна глава;
  `max_chapter_paragraph_count` без самого H1; `max_paragraph_chars` после слияний; границы 500/501, 400/401,
  5000/5001 (ровно на пороге — не превышение); `exceeded` в фиксированном порядке.
- [ ] **T-B5** `chapter_level`, `heading_levels_present`, `demoted_heading_count` (серия считается один раз).

**C. Реализация**
- [ ] **T-B6** `pipeline/narration_document.py`: константы, датаклассы, `build_narration_document_plan`. Без импорта
  python-docx, Streamlit, I/O.

**D. Проверка**
- [ ] **T-B7** `tests/test_spec_072_narration_document.py`. Done: зелёный; гард импорта (модуль не импортирует `docx`,
  `streamlit`).

---

## WP-C. Рендерер DOCX (FR-004)

**Ветка**: `072/wp-c-docx` | **Worktree**: `D:\Temp\claude\wt-072-docx` | **Агент**: Sonnet / medium |
**Сначала слиты**: ничего | **Владеет**: `src/docxaicorrector/generation/narration_docx.py` (нов.),
`tests/test_spec_072_narration_docx.py` (нов.). Решения — research R4, R5; контракт — `contracts/result-group.md` §4.

**B. Падающие тесты** (модуля нет — все падают)
- [ ] **T-C1** Дословность: абзацы с `*звёзды*`, `_черта_`, `# решётка`, `<угол>`, `> знак`, тире в начале строки,
  U+0301 (`за\u0301мок`), заглавная гласная (`замОк`), `ё`, одиночный `\n` → `docx.Document(BytesIO(bytes)).paragraphs[i].text`
  равен входу побайтно; у абзаца с `\n` в XML есть `<w:br/>`.
- [ ] **T-C2** Стили: только `Heading 1` и `Normal`; `Normal` и `Heading 1` — `Times New Roman` в `w:ascii`, `w:hAnsi`,
  `w:cs`, `w:eastAsia`, без атрибутов темы.
- [ ] **T-C3** Структура: число абзацев = числу входных; пустых абзацев нет; в zip нет `word/header*.xml`,
  `word/footer*.xml`, нет `w:fldSimple`/`w:instrText` (поле оглавления), картинок (`word/media/`), таблиц (`w:tbl`).
- [ ] **T-C4** Свойства: `title` = переданное; `author` и `comments` пустые.
- [ ] **T-C5** Текст с `\x0b` → исключение выходит наружу (его ловит WP-H).

**C. Реализация**
- [ ] **T-C6** `generation/narration_docx.py`: `render_narration_docx(paragraphs, *, title) -> bytes`. К
  `section.header`/`footer` не обращаться (research R4).

**D. Проверка**
- [ ] **T-C7** `tests/test_spec_072_narration_docx.py`. Done: зелёный.

---

## WP-D. Экспорт PDF, общий помощник процесса, шрифты (FR-005)

**Ветка**: `072/wp-d-pdf` | **Worktree**: `D:\Temp\claude\wt-072-pdf` | **Агент**: Sonnet / high |
**Сначала слиты**: ничего | **Владеет**: `src/docxaicorrector/runtime/external_process.py` (нов.),
`src/docxaicorrector/generation/narration_pdf.py` (нов.), `system-requirements.apt`, `scripts/setup-wsl.sh`,
`tests/test_spec_072_narration_pdf.py` (нов.), `tests/test_spec_072_narration_pdf_system.py` (нов., `system_deps`).
Решения — research R5–R8, R14; контракт — `contracts/result-group.md` §3; сущности — `data-model.md` §4.

**B. Падающие тесты — CI-часть** (`tests/test_spec_072_narration_pdf.py`, подменённые `runner`/`find_soffice`)
- [ ] **T-D1** Команда: `[soffice, "-env:UserInstallation=file:///…/lo_profile", "--headless", "--norestore",
  "--convert-to", NARRATION_PDF_FILTER, "--outdir", tmp, tmp/"<stem>.tts.docx"]`; `cleanup_process_group=True`,
  `timeout_seconds=60`; входной файл содержит переданные байты.
- [ ] **T-D2** Два вызова — разные каталоги профиля; после возврата временного каталога нет (и при успехе, и при отказе).
- [ ] **T-D3** Причины: finder → `None` → `soffice_not_found`, runner не вызван; `RuntimeError` с «Превышено время
  ожидания» → `timeout`; иной `RuntimeError`/`OSError` → `failed`; файла нет → `missing_output`; 0 байт → `empty_output`;
  не `%PDF-` → `not_pdf`; успех → байты, `reason is None`, `seconds > 0`. Ни один случай не бросает исключение.
- [ ] **T-D4** `runtime/external_process.py`: `run_completed_process` по тайм-ауту вызывает `terminate_process_tree`
  (перенос теста `tests/test_processing_runtime.py:1414-1450` в новую форму, сам тот тест не трогать — его переводит
  WP-F); `find_soffice_binary` — `soffice`, иначе `libreoffice`, иначе `None` (подмена `shutil.which`).
- [ ] **T-D5** Статика: `system-requirements.apt` содержит `fonts-liberation`; `scripts/setup-wsl.sh` проверяет
  `fc-list ":lang=ru:family=Liberation Serif"` (падает: строк нет).

**B'. Системные тесты** (`tests/test_spec_072_narration_pdf_system.py`, `pytestmark = pytest.mark.system_deps`; без
`soffice` — `skip`, при `DOCXAI_REQUIRE_REAL_DOCUMENT_CAPABILITIES` — падение). DOCX строится в тесте локальным
помощником python-docx с тем же шрифтом (от WP-C не зависит); набор — вымышленные абзацы, ≈ 60, 3 `Heading 1`, без
комбинирующих знаков.
- [ ] **T-D6** SC-003: текст pdfminer без пробельных символов = ожидаемый; каждый абзац находится по порядку, хвоста
  нет; набор непуст; закладки уровня 1 = тексты `Heading 1` по порядку; у всех шрифтов `FontFile*`. Отрицательные
  контроли той же функцией сравнения: выпавший абзац, лишний дубль — не равны.
- [ ] **T-D7** SC-006: два `export_narration_pdf` в двух потоках — оба PDF проходят T-D6; число процессов `soffice`
  после теста не выросло.

**C. Реализация**
- [ ] **T-D8** `runtime/external_process.py` — дословный перенос `_run_completed_process`/`_terminate_process_tree`
  (`processing/processing_runtime.py:321-410`) под публичными именами + `find_soffice_binary`. `processing_runtime` НЕ
  трогать (WP-F).
- [ ] **T-D9** `generation/narration_pdf.py` по `data-model.md` §4.
- [ ] **T-D10** [P] `system-requirements.apt` (+`fonts-liberation`), `scripts/setup-wsl.sh` (`verify_runtime`).

**D. Проверка**
- [ ] **T-D11** Отдельными командами: `tests/test_spec_072_narration_pdf.py`,
  `tests/test_spec_072_narration_pdf_system.py -m system_deps`, `tests/test_script_contract_static.py` (кроме гарда
  инвентаря). Done: зелёные; в выводе системного теста — время конвертации.

---

## WP-E. Группа результата и хранение (FR-007, файлы)

**Ветка**: `072/wp-e-result-group` | **Worktree**: `D:\Temp\claude\wt-072-group` | **Агент**: Sonnet / medium |
**Сначала слиты**: ничего | **Владеет**: `src/docxaicorrector/runtime/artifacts.py`,
`src/docxaicorrector/runtime/artifact_retention.py`, `tests/test_spec_072_result_group.py` (нов.). Решение — research R12;
контракт — `contracts/result-group.md` §1.

**A. Характеристика**
- [ ] **T-E1** Без новых аргументов: состав группы, имена файлов и `artifact_paths` `write_ui_result_artifacts` — снимок,
  зелёный до и после.

**B. Падающие тесты**
- [ ] **T-E2** `narration_docx_bytes`/`narration_pdf_bytes` → файлы `<stem>.tts.docx`/`.tts.pdf` с этими байтами,
  ключи `tts_docx_path`/`tts_pdf_path`; `None` или `b""` → файла и ключа нет (падает: аргументов нет).
- [ ] **T-E3** Сбой записи одного члена (подмена `Path.write_bytes` на `.tts.pdf`-временном файле → `OSError`) — в
  каталоге не остаётся ни одного файла группы, ни временных (`_atomic_write_group`).
- [ ] **T-E4** Хранение: группа с `.tts.docx`/`.tts.pdf` старше срока или сверх числа удаляется ЦЕЛИКОМ, оба новых
  файла — тоже (падает: сегодня они «passthrough», `runtime/artifact_retention.py:206-209`, и не удаляются никогда);
  ключ группы `x.result.tts.docx` → `x`.

**C. Реализация**
- [ ] **T-E5** `runtime/artifacts.py:363-446` (аргументы, пути, `group_entries`, `artifact_paths`);
  `runtime/artifact_retention.py:90-97` (+`.result.tts.docx`, `.result.tts.pdf` перед `.result.docx`; докстринг `:184-188`).

**D. Проверка**
- [ ] **T-E6** Отдельными командами: `tests/test_spec_072_result_group.py`, `tests/test_runtime_artifacts.py`,
  `tests/test_session_artifact_isolation.py`. Done: зелёные.

---

## WP-G. Экран аудиокниги (FR-009)

**Ветка**: `072/wp-g-screen` | **Worktree**: `D:\Temp\claude\wt-072-screen` | **Агент**: Sonnet / medium |
**Сначала слиты**: ничего (контракт bundle — `contracts/state-bundle.md` §2, ключ фиксирован) | **Владеет**:
`src/docxaicorrector/ui/_ui.py`, `src/docxaicorrector/ui/_app.py`, `src/docxaicorrector/ui/locales/ru.json`,
`src/docxaicorrector/ui/locales/en.json`, `tests/test_spec_072_result_screen.py` (нов.), `tests/test_ui.py` (только
случаи аудиокниги, если их ожидания меняются). Решение — research R10; контракты — `contracts/state-bundle.md` §3–4,
`contracts/result-group.md` §2.

**A. Характеристика**
- [ ] **T-G1** Для `edit` и `translate` (`narration_text=None`): метки, порядок, имена и MIME кнопок
  `render_result_bundle` — снимок через двойник `st` (как в `tests/test_ui.py`), зелёный до и после.

**B. Падающие тесты** (`tests/test_spec_072_result_screen.py`; рендер с двойником `st`/`AppTest`)
- [ ] **T-G2** Аудиокнига, все форматы: подпись «Текст для озвучки», кнопки DOCX (`type="primary"`), PDF, TXT в этом
  порядке; подпись «Для проверки», кнопки DOCX для проверки и Markdown; все `width="stretch"`; имена
  `<stem>.tts.docx`/`.tts.pdf`/`.tts.txt`; MIME по `contracts/result-group.md` §2 (падает: сегодня три кнопки в одной строке).
- [ ] **T-G3** Нет PDF (`pdf_bytes=None`, причина `timeout`): две кнопки и `st.caption` с текстом
  `result.narration_pdf_unavailable.timeout`; нет DOCX — кнопки PDF/DOCX нет, строка `result.narration_docx_unavailable`.
- [ ] **T-G4** Старый bundle (`narration_exports` отсутствует) — одна кнопка TXT, строка «Для проверки», без исключения
  (SC-007). Заблокированная выдача — все кнопки `secondary`.
- [ ] **T-G5** `_render_completed_result_view` передаёт `result.get("narration_exports")`. Каждый новый ключ локали есть
  в `ru.json` и `en.json`; в `ui/` нет `use_container_width`.

**C. Реализация**
- [ ] **T-G6** `ui/_ui.py`: `_build_narration_docx_filename`, `_build_narration_pdf_filename` (рядом с `:92`), аргумент
  `narration_exports` у `render_result_bundle` (`:1078`), ветвь аудиокниги `:1195-1236` — две строки; ветвь
  перевода/редактуры `:1239-1264` не трогать. `ui/_app.py:904-919` — передать поле.
- [ ] **T-G7** [P] Локали — ключи `contracts/state-bundle.md` §4, `contracts/events.md` (notice лимитов).

**D. Проверка**
- [ ] **T-G8** Отдельными командами: `tests/test_spec_072_result_screen.py`, `tests/test_ui.py`,
  `tests/test_ui_i18n.py`, `tests/test_ui_review_presentation.py`, `tests/test_acceptance_verdict_on_screen.py`.
  Done: зелёные. Браузер — после слияния всего (T-Z4).

---

## WP-F. Состояние, bundle, общий поиск `soffice` (FR-008, FR-005)

**Ветка**: `072/wp-f-state` | **Worktree**: `D:\Temp\claude\wt-072-state` | **Агент**: Sonnet / medium |
**Сначала слиты**: WP-D | **Владеет**: `src/docxaicorrector/processing/processing_runtime.py`,
`src/docxaicorrector/processing/processing_service.py`, `src/docxaicorrector/runtime/state.py`,
`tests/test_spec_072_state_bundle.py` (нов.), `tests/test_processing_runtime.py` (только цель подмены в тесте
`:1414-1450`). Решения — research R8, R10; контракт — `contracts/state-bundle.md` §1–2.

**A. Характеристика**
- [ ] **T-F1** Импорт PDF/DOC: существующие `tests/test_processing_runtime.py` (`:1404-1760`, `:2240-2290`) зелёные до и
  после — без правок, кроме T-F6.

**B. Падающие тесты** (`tests/test_spec_072_state_bundle.py`)
- [ ] **T-F2** `_filter_allowed_set_state_values({"latest_narration_exports": {...}})` пропускает ключ без WARNING
  `state_event_unknown_keys` (падает: ключ отбрасывается).
- [ ] **T-F3** `build_result_bundle(..., narration_exports=…)` нормализует (лишние ключи прочь, не-`bytes` → `None`);
  `get_current_result_bundle` кладёт `narration_exports` только при `latest_narration_text is not None` (правило пары);
  без ключа в сессии — `None`.
- [ ] **T-F4** `init_session_state` → `None`; `reset_run_state` (оба режима) обнуляет; аварийный обработчик рабочего
  потока до доставки обнуляет вместе с `latest_narration_text`, после доставки — нет (как текст).
- [ ] **T-F5** Один поиск: в `processing_runtime.py` нет `shutil.which("soffice")` (проверка исходника);
  `_convert_pdf_to_docx`, `_convert_legacy_doc_to_docx`, `legacy_doc_conversion_available` зовут
  `find_soffice_binary`; `processing_runtime._run_completed_process is external_process.run_completed_process`.

**C. Реализация**
- [ ] **T-F6** `processing_runtime.py`: ключ в `:164-180`; `build_result_bundle` (`:1689`) и
  `get_current_result_bundle` (`:1778`); удалить тела `_run_completed_process`/`_terminate_process_tree` (`:321-410`),
  импортировать из `runtime.external_process` под прежними именами; три поиска → `find_soffice_binary()`. В
  `tests/test_processing_runtime.py:1414-1450` подмену `_terminate_process_tree` перевести на
  `runtime.external_process.terminate_process_tree`.
- [ ] **T-F7** `runtime/state.py:602-615`, `:658-760` (init/reset); `processing/processing_service.py:375-381`.

**D. Проверка**
- [ ] **T-F8** Отдельными командами: `tests/test_spec_072_state_bundle.py`, `tests/test_processing_runtime.py`,
  `tests/test_state.py`, `tests/test_processing_service.py`, `tests/test_app_restartable_state.py`,
  `tests/test_session_state_ownership.py`, `tests/test_real_document_validation_corpus.py -m system_deps`. Done: зелёные.

---

## WP-H. Поздний этап: интеграция (FR-003 (в), FR-005 вызов, FR-006, FR-007 событие и запись)

**Ветка**: `072/wp-h-late-phase` | **Worktree**: `D:\Temp\claude\wt-072-late` | **Агент**: **Opus** / high |
**Сначала слиты**: WP-A, WP-B, WP-C, WP-D, WP-E, WP-F | **Владеет**: `src/docxaicorrector/pipeline/narration_exports.py`
(нов.), `src/docxaicorrector/pipeline/late_phases.py`, `tests/test_spec_072_late_phase_exports.py` (нов.),
`tests/test_spec_072_exports_system.py` (нов., `system_deps`), `tests/test_late_phases_finalize_gate_persistence.py`
(только если ожидания `emit_state`/писателя меняются). Решение — research R9; контракты — `contracts/events.md`,
`contracts/state-bundle.md` §1; сущности — `data-model.md` §5.

**A. Характеристика**
- [ ] **T-H1** Для `translate`/`edit` через поздний этап с двойниками: аргументы `emit_state` и писателя группы — снимок
  (ни `latest_narration_exports`, ни байтов озвучки), зелёный до и после; экспорт не вызывается (двойник считает).

**B. Падающие тесты** (`tests/test_spec_072_late_phase_exports.py`; записи → `_build_narration_text` → поздний этап,
писатель и `export_narration_pdf` подменены на `pipeline.narration_exports`)
- [ ] **T-H2** SC-001: синтетический набор (T-A1 + серии `2 → 1`, `1 → 2`, `3 → 3`, заголовок в конце) → абзацы
  `.tts.docx` (открыть байты из `emit_state`) = абзацы `.tts.txt` с ровно перечисленными слияниями (по ID из
  `heading_merges`), побайтно; отрицательные контроли той же функцией сравнения: выпавший абзац, лишний дубль, абзац
  тела, ставший `Heading 1` — не равны.
- [ ] **T-H3** SC-005: экспорт возвращает `soffice_not_found` / `timeout` → прогон успешен, писатель получил
  `narration_docx_bytes` и `narration_pdf_bytes=None`, `latest_narration_exports.pdf_unavailable_reason` = причина,
  WARNING `audiobook_narration_pdf_unavailable` с причиной, поля события (`narration_pdf_status="unavailable"`).
- [ ] **T-H4** Рендерер бросает → ERROR `audiobook_narration_docx_failed`, PDF не пробуется
  (`docx_not_built`), `.tts.txt` и DOCX для проверки выданы (Anti-regression 3).
- [ ] **T-H5** Stop перед экспортом → прогон «остановлен», экспорт не вызван, `latest_narration_exports` не
  опубликован.
- [ ] **T-H6** Поля `ui_audiobook_artifact_saved` по `contracts/events.md` (все новые ключи всегда; прежние ключи спеки
  070 на месте — Anti-regression 6); `audiobook_studio_limits_exceeded` и notice `result.audiobook_studio_limits_exceeded`
  — только при превышении (набор с главой из 401 абзаца); в событиях нет текстов абзацев.
- [ ] **T-H7** Системный e2e (`tests/test_spec_072_exports_system.py`, `system_deps`): записи → группы → план → DOCX →
  реальный `export_narration_pdf` → проверка T-D6 на продуктовом файле.

**C. Реализация**
- [ ] **T-H8** `pipeline/narration_exports.py`: `NarrationExports`, `build_narration_exports`, три события.
- [ ] **T-H9** `pipeline/late_phases.py`: граница Stop и вызов после `:1273-1298` (только `audiobook`, текст есть);
  `latest_narration_exports` в `emit_state` `:1372-1391`; аргументы писателя `:1411-1434`; поля события `:1544-1565`;
  notice лимитов.

**D. Проверка**
- [ ] **T-H10** Отдельными командами: `tests/test_spec_072_late_phase_exports.py`,
  `tests/test_spec_072_exports_system.py -m system_deps`, `tests/test_late_phases_finalize_gate_persistence.py`,
  `tests/test_audiobook_pass.py`, `tests/test_document_pipeline.py`, `tests/test_spec_070_request_golden.py`. Done: зелёные.

---

## WP-I. Раннер, гард событий, документы (FR-007 раннер, FR-010)

**Ветка**: `072/wp-i-runner-docs` | **Worktree**: `D:\Temp\claude\wt-072-runner` | **Агент**: Sonnet / medium
(документы — можно Haiku) | **Сначала слиты**: WP-H | **Владеет**:
`tests/artifacts/real_document_pipeline/run_lietaer_validation.py`, `tests/test_real_document_pipeline_validation.py`,
`scripts/_list_log_events.py`, `docs/LOGGING_AND_ARTIFACT_RETENTION.md`, `AGENTS.md` (только раздел «UI result
artifacts»), `README.md` (абзац «ElevenLabs Audiobook Mode», `:507-514`), `docs/WORKFLOW_AND_IMAGE_MODES.md` (`:140-148`).
Решение — research R13; контракт — `contracts/events.md`.

**B. Падающие тесты** (`tests/test_real_document_pipeline_validation.py`)
- [ ] **T-I1** `_SPEC_072_LOG_EVENTS` = три новых события + `ui_audiobook_artifact_saved`: каждое эмитится в `src/` и
  зарегистрировано в документе логирования (по образцу `:7962-7973`).
- [ ] **T-I2** Отчёт на синтетическом логе и состоянии: `narration_artifact` несёт новые поля; строки сводки
  `narration_heading1_count=…` и т. д.; `output_artifacts` — `tts_docx_path`, `tts_pdf_path`, `latest_*`,
  `tts_docx_openable`, `tts_docx_heading1_count`, `tts_docx_other_heading_style_count`; нет события — `not_reported`, не 0.
- [ ] **T-I3** Раннер пишет `.tts.docx`/`.tts.pdf` из `state["latest_narration_exports"]` в каталог прогона и копирует в
  `latest`; без ключа — пути `null`, исключения нет.

**C. Реализация**
- [ ] **T-I4** Раннер (`:5011-5039`, `:6360`, `:6386-6414`, `:6519-6540`, `:6798`, `:1595-1632`).
- [ ] **T-I5** [P] `scripts/_list_log_events.py` — `TARGETS` += `pipeline/narration_exports.py`,
  `generation/narration_pdf.py`.
- [ ] **T-I6** [P] FR-010: `docs/LOGGING_AND_ARTIFACT_RETENTION.md` — §3.11 (три события), §5.5 (новые поля
  `ui_audiobook_artifact_saved`, `artifact_paths` с `tts_docx_path`/`tts_pdf_path` у `ui_result_artifacts_saved`, `:415`),
  retention `.run/ui_results/` (`:384`: `.result.tts.docx`, `.result.tts.pdf` в группе), Changelog; AGENTS.md «UI result
  artifacts» (`:462-467`): стем-группа с `.result.tts.docx`/`.result.tts.pdf`, и строка `:466` — без устаревших
  `mode` / `tag_count` / `excluded_blocks`, с полями спеки 070/072; README (`:509-511`) и `docs/WORKFLOW_AND_IMAGE_MODES.md`
  (`:145`, `:146`) — три формата озвучки и две строки кнопок.

**D. Проверка**
- [ ] **T-I7** Отдельными командами: `tests/test_real_document_pipeline_validation.py`,
  `tests/test_agent_contract_consistency.py`, `tests/test_documentation_links.py`, `tests/test_script_contract_static.py`
  (кроме гарда инвентаря). Done: зелёные.

---

## Приёмка (оркестратор)

- [ ] **T-Z1** Слияния в `072/integration`: волна 1 (A, B, C, D, E, G — любой порядок), F, H, I. Каждый перенос — на
  свежую интеграционную ветку; при каждом слиянии — строки новых тестов пакета в `docs/testing/TEST_TIER_INVENTORY.md`
  (`## Unit-Contract`; `*_system.py` — `## System-Deps`).
- [ ] **T-Z2** После КАЖДОГО слияния — полный прогон в ГЛАВНОМ дереве:
  `wsl.exe -d Debian --cd "D:\Work\Projects\DocxAICorrector" -- bash scripts/test.sh tests/ -q`; системные тесты 072
  отдельными командами (`quickstart.md` §5); перед «всё зелёное» — `git status --porcelain` пуст, `git diff --check` чист.
- [ ] **T-Z3** Гарды в главном дереве, каждый отдельной командой: `tests/test_spec_status_consistency.py`,
  `tests/test_where_we_are_freshness.py`, `tests/test_documentation_links.py`, `tests/test_script_contract_static.py`,
  `tests/test_typecheck.py` (≥ 180 с; новых ошибок нет).
- [ ] **T-Z4** FR-009 — проверка экрана во встроенном браузере (`quickstart.md` §5): две строки кнопок, порядок,
  растяжение, имена скачанных файлов; DOCX открывается, PDF с закладками. Если платный прогон для экрана не
  согласован — сказать прямо, что браузер проверял только рендер-тест WP-G.
- [ ] **T-Z5** Расширенное ревью Codex `gpt-6-astra`, `--sandbox read-only` (SC-008), по рецепту AGENTS.md
  («Обязательная приёмка оркестратора») ДО слияния в `main`: самый свежий `codex.exe` (`Sort-Object LastWriteTime
  -Descending`), промпт файлом через stdin, ответ в файл, в фоне. Объём — все затронутые поверхности: модули с
  изменённым hunk целиком (список из `git diff --stat f6de2fd..<head>`), прямые вызывающие/вызываемые
  (`block_execution.finalize_audiobook_block_for_delivery`, `late_phases` до и после экспорта, `processing_runtime`
  импорт PDF/DOC, `ui/_app._render_completed_result_view`), их тесты; в промпте — base/head SHA, команды `git diff
  --stat` и `git log --oneline`, литеральные абсолютные пути, путь к спеке и плану, отдельным абзацем что измерено
  оператором (замеры `research.md` R5–R7, R11; WSL ему закрыт, данные `D:\Temp\docxai-research\072\` — читать и считать
  может); требовать `file:line`, частоту и чем измерена, уверенность, вердикт последней строкой из фиксированного
  набора; формулировки без «атакуй/сломай». Каждую находку проверить по коду и приземлить (правка с тестом / Changelog
  / Non-goals). Отчёт — `docs/reviews/CODEX_REVIEW_072_<YYYY-MM-DD>.md` с промптом и таблицей «поднято / вердикт /
  замерено».
- [ ] **T-Z6** После правок по ревью — снова T-Z2/T-Z3; статус спеки и `docs/WHERE_WE_ARE.md`; слияние
  `072/integration` в `main`, push.
- [ ] **T-Z7** Спека не объявляется закрытой до WP-Y (или до явного решения владельца закрыть без замера).

## WP-Y. Замер FR-011 (оркестратор, ПЛАТНО — нужно согласие владельца)

- [ ] **T-Y1** [?] [$] Согласие владельца на сумму (≈ 0,35 $, прогон полной переведённой Money).
- [ ] **T-Y2** [$] Канонический прогон (`quickstart.md` §6). При падении профиля — свежий run report, `failed_checks`
  дословно с `actual` / `threshold` и отношением, только потом гипотезы.
- [ ] **T-Y3** Читать по таблице `quickstart.md` §6: файлы, `heading1_count` против прогноза 23, слияния против 8,
  лимиты, PDF; равенство SC-001 на реальных данных — скрипт оркестратора над `.tts.txt` и `.tts.docx` прогона (вне git).
- [ ] **T-Y4** [?] Владелец загружает `.tts.docx` в ElevenLabs Studio и сообщает число глав и нет ли потерянного текста
  до первой главы. Итоги — в Changelog спеки как есть.
