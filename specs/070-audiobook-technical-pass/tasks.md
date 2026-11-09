# Tasks: аудиокнига — технический проход по готовому тексту

**Spec**: [spec.md](spec.md) | **Plan**: [plan.md](plan.md) (раздел «Порядок реализации: пакеты работ») |
**Контракты**: [contracts/](contracts/) | **Данные**: [data-model.md](data-model.md), [research.md](research.md) |
**Проверка**: [quickstart.md](quickstart.md)

Tier: полный цикл (Конституция, принцип III). Задачи сгруппированы по пакетам WP-A…WP-I; порядок внутри пакета всегда
один: (A) характеристические / золотые тесты того, что НЕ должно измениться → (B) падающие тесты нового поведения
(анти-вакуум: у каждого сказано, чем доказано, что он падает без правки) → (C) реализация → (D) каноническая проверка
пакета. Пакет владеет ТОЛЬКО перечисленными у него файлами (Конституция VI); правка вне перечня запрещена — нужда в ней
возвращается оркестратору вопросом.

## Формат и общие правила

- `T-<пакет><номер>`; `[P]` — можно параллельно с соседними задачами того же пакета (разные файлы, нет зависимости);
  `[?]` — решение оркестратора/владельца, агент не гадает. Между пакетами параллельность задана волнами.
- **База и точка ребейза**: `main` @ `fdf775f` (слита ветка 062). Ссылки `file:line` плана сверены там; если
  интеграционная ветка создана от более свежего `main` — сверить заново (Конституция VIII), расхождение — вопрос
  оркестратору, не догадка.
- **Каноническая проверка пакета** — одна команда на один selector, selector ДО опций pytest:
  `wsl.exe -d Debian --cd "D:\Temp\claude\wt-070-<slug>" -- bash scripts/test.sh <selector> -q`
  (`.venv` в боковом worktree — симлинк на главное дерево). Из Git Bash `$VAR` на границе `wsl.exe` схлопывается — только
  литеральные пути, без циклов `for`. Голый `python` / `.venv-win` / `py -m pytest` запрещены (debug-путь — только с
  пометкой `debug-only`). Оборванный вывод — сначала проблема транспорта; сужать до node selector.
- **Тесты истории** (`test_spec_status_consistency` и т.п.) в боковом worktree пропускаются; проверяются в главном дереве
  (T-Z3). `git` в боковом worktree под WSL не работает — коммиты и `git diff --check` из Git Bash в worktree.
- **Конституция VII**: ни в коде, ни в тестах, ни в промптах нет текста книг, литералов книг корпуса и словарей слов;
  примеры — вымышленные, той же ФОРМЫ. Классы символов — по категориям/свойствам Unicode закреплённой версии.
- **Новый тестовый файл** → строка в `docs/testing/TEST_TIER_INVENTORY.md` `## Unit-Contract` в той же ветке (гард
  `tests/test_script_contract_static.py:363`).
- **LF** во всех новых файлах; после правок `git diff --check`. Полные тексты в лог не пишутся.
- Тема коммита пакета: `spec 070: <что сделано>`.

## Волны и зависимости

```text
T-01 (оркестратор): 070/integration от fdf775f, worktrees, T-D0 решено
волна 1 (параллельно):  WP-A  WP-C  WP-D  WP-E  WP-F        слияние: A, затем C, D, E, F
волна 2:                WP-B  ← A
волна 3:                WP-G  ← A, B, C, D, E, F
волна 4:                WP-H  ← G   (T-H0 решено)
приёмка:                T-Z1…T-Z5 → WP-I (платно, по согласию владельца)
```

Критический путь: **WP-A → WP-B → WP-G → WP-H**. WP-C/D/E/F укладываются в волну 1 с запасом.

## Подготовка (оркестратор)

- [ ] **T-01** Создать `070/integration` от `fdf775f` (записать SHA в Changelog спеки при первом слиянии); worktrees
  `D:\Temp\claude\wt-070-{postpass,prompt,exclusion,cleanup,repair}` для волны 1 с симлинком `.venv`.
- [ ] **T-02** [?] Обновить статус спеки и `docs/WHERE_WE_ARE.md` вместе с первым слиянием (иначе
  `test_spec_status_consistency` / `test_where_we_are_freshness` красны в главном дереве).

---

## WP-A. Удаление второго прохода, тегов и мёртвых правил обзора (FR-002, D-3, FR-006 последнее предложение)

**Ветка**: `070/wp-a-postpass-removal` | **Worktree**: `D:\Temp\claude\wt-070-postpass` | **Агент**: Sonnet / medium
(документы T-A10 — можно Haiku) | **Сначала слиты**: ничего | **Владеет**: см. таблицу плана (строка WP-A).
Перечень мест — таблица FR-002 и «Тестовые поверхности» `docs/reviews/CODEX_REVIEW_070_SPEC_2026-11-09.md:252-283`
(строки сверить на `fdf775f`; файлы 062 сдвинуты).

**A. Характеристика**
- [ ] **T-A1** Записать (тест, зелёный на `fdf775f`): `_build_narration_text` для `translate`/`edit` без второго прохода
  возвращает `None`; аргументы промпта и запрос блока `translate`/`edit` — их закрепит WP-C (здесь не дублировать).

**B. Падающие тесты** (`tests/test_spec_070_postpass_removed.py`, нов.)
- [ ] **T-A2** Пользовательский `config.toml` с `audiobook_postprocess_default = true` → WARNING `config_key_ignored`,
  называющий ключ (падает на `fdf775f`: ключ читается, `core/config_runtime_sections.py:528`).
- [ ] **T-A3** `AppTest`: в сайдбаре `edit` и `translate` нет виджета `sidebar_audiobook_postprocess`; `render_sidebar`
  возвращает 12 значений (падает: 13).
- [ ] **T-A4** `corpus_registry.toml`: нет профиля `ui-parity-translate-audiobook-postprocess`, ни один профиль не несёт
  `audiobook_postprocess_enabled`; `RunProfile` не принимает поле (неизвестный ключ — ошибка, как прочие) (падает).
- [ ] **T-A5** Импорт `_run_audiobook_postprocess`, `_project_final_cleanup_narration_chunks`,
  `_should_run_audiobook_postprocess`, `_ELEVENLABS_TAG_PATTERN` из `pipeline.narration_postprocess` и
  `pipeline.late_phases` → `ImportError`/`AttributeError` (падает: имена есть).
- [ ] **T-A6** Обзор narration: текст с `[[DOCX_IMAGE_x]]`, `https://…`, `# Заголовок`, `[тег]` не даёт правил
  `internal_placeholder`, `raw_url`, `markdown_heading`, `disallowed_tags`; `doi`/`isbn_identifier`/`inline_citation`
  срабатывают как раньше, `match_count` — вхождения (падает на первых четырёх).

**C. Реализация**
- [ ] **T-A7** `pipeline/narration_postprocess.py`: удалить второй проход, теги, мёртвые правила (план, §FR-002);
  `_collect_narration_chunks` и `_assemble_narration_recording_joins` оставить.
- [ ] **T-A8** `pipeline/late_phases.py` (реэкспорты, ошибки второго прохода, `narration_mode`, shortfall, `tag_count`,
  поле результата), `pipeline/contracts.py:306-312`, `runtime/state.py`, `processing/processing_runtime.py` (поле
  результата и его восстановление), `ui/_ui.py`, `ui/_app.py`, `ui/locales/{ru,en}.json`, `validation/profiles.py`,
  `core/config.py:272`, `core/config_loader_layers.py:180`, `core/config_runtime_sections.py:528,574-576,603`,
  комментарии `block_execution.py:1764-1766`, `text_call_support.py:4`.
- [ ] **T-A9** `corpus_registry.toml` (профиль и поле), раннер (`run_lietaer_validation.py:5000-5030`: поля
  `postprocess_*`, `tag_count`, `mode`), `resources/config.toml` (упоминание второго прохода в комментарии `:114`).
- [ ] **T-A10** [P] Документы: `README.md`, `docs/RUNNING_THE_PIPELINE.md`, `docs/WORKFLOW_AND_IMAGE_MODES.md`,
  `docs/testing/REAL_DOCUMENT_VALIDATION_WORKFLOW.md`, `docs/LOGGING_AND_ARTIFACT_RETENTION.md` (§3.3 `:135-137`, §3.8
  `:234`, §5.5 `:395`; удалённые события — запись «удалено спекой 070», как у 054). Исторические спеки/ревью/сводки не
  трогать.
- [ ] **T-A11** Тесты по перечню Codex (`test_document_pipeline`, `test_paragraph_record_and_production_verdict`,
  `test_spec_063_apparatus_policy`, `test_real_document_pipeline_validation`, `test_config`, `test_app_preparation`,
  `test_app_restartable_state`, `test_application_flow`, `test_processing_runtime`, `test_session_state_ownership`,
  `test_state`, `test_ui`): удалить проверки удалённого поведения; проверки, которые остаются верными, сохранить.

**D. Проверка**
- [ ] **T-A12** Отдельными командами: `tests/test_spec_070_postpass_removed.py`, `tests/test_config_keys_are_read.py`,
  `tests/test_config.py`, `tests/test_ui.py`, `tests/test_document_pipeline.py`, `tests/test_real_document_pipeline_validation.py`,
  `tests/test_real_document_validation_corpus.py`; `git grep -n "audiobook_postprocess\|AUDIOBOOK_POSTPROCESS"` в `src/`,
  `tests/`, раннере, `corpus_registry.toml` и действующих документах — пусто (кроме Changelog'ов). Done: зелёные,
  `git diff --check` чист.

---

## WP-C. Системный шаблон аудиокниги, промпты, золотые запросы (FR-004, SC-004)

**Ветка**: `070/wp-c-prompt` | **Worktree**: `D:\Temp\claude\wt-070-prompt` | **Агент**: Sonnet / medium |
**Сначала слиты**: ничего | **Владеет**: строка WP-C таблицы плана. Контракт: `contracts/prompts.md`; решение — R3.

**A. Золотые тесты SC-004 (ДО любой правки)**
- [ ] **T-C1** `tests/test_spec_070_request_golden.py` (нов.): SHA-256 `load_system_prompt(...)` по матрице R3
  (`translate`/`edit` × варианты × все интенсивности × пары `en→ru`, `auto→ru`, `ru→ru`, `de→en` × контекст `""`/вымышленный)
  и словари `build_system_prompt_arguments` на двойниках контекста. Хеши получить ОДИН раз на `fdf775f` каноническим
  путём (`bash scripts/test.sh` теста-генератора с выводом, затем вписать литералами). Done: зелёный на `fdf775f` без
  единой правки кода; результат записан.

**B. Падающие тесты** (`tests/test_audiobook_prompt.py`, нов.)
- [ ] **T-C2** Свойства §0 контракта: промпт `audiobook` одинаков при любых языках/интенсивности/контексте; нет
  `{…}`, `[[IF`, текстов `editorial_intensity_*.txt`, правил «Markdown-заголовки», «HTML-таблицы», плейсхолдеров
  картинок, тегов формы `[слово]`; есть правило маркеров и запрет пустого абзаца. Анти-вакуум: падает на текущем
  шаблоне (в нём `{target_language}`, интенсивность, правила 4–7 `system_prompt.txt:46-52`).
- [ ] **T-C3** `prompt_variant="repair"` для `audiobook`: тот же шаблон, инструкции `operation_audiobook_repair.txt`, без
  секции примера; `repair` для `translate`/`edit` → `RuntimeError` (падает: варианта нет).
- [ ] **T-C4** `build_system_prompt_arguments` для `audiobook` не читает `editorial_intensity_default` и отдаёт пустые
  языки/интенсивность (падает: сейчас `literary` и пара).

**C. Реализация**
- [ ] **T-C5** Ветвь `audiobook` в `load_system_prompt` (`core/config.py:1751`) до нормализации (`:1769`) и валидации
  (`:1773`); пути новых файлов рядом с `_PROMPT_OPERATION_PATHS` (`:239`).
- [ ] **T-C6** [P] Файлы промптов по контракту: `system_prompt_audiobook.txt` (нов.), `operation_audiobook.txt`,
  `example_audiobook.txt` (переписаны), `operation_audiobook_repair.txt` (нов.). Общий `system_prompt.txt` не трогать.
- [ ] **T-C7** `pipeline/support.py:26-45` — аргументы для `audiobook`.
- [ ] **T-C8** Удалить `tests/test_config.py:917-1002` (проверки наличия фраз — FR-010); обновить случай `audiobook` в
  `tests/test_generation_request_profile.py` (намеренно: новый шаблон) — случаи `translate`/`edit` НЕ менять.

**D. Проверка**
- [ ] **T-C9** Отдельными командами: `tests/test_spec_070_request_golden.py` (зелёный ДО и ПОСЛЕ — доказательство SC-004),
  `tests/test_audiobook_prompt.py`, `tests/test_generation_request_profile.py`, `tests/test_config.py`,
  `tests/test_prompts_carry_no_corpus_literals.py`. Done: зелёные.

---

## WP-D. Исключение по абзацу и план блока (FR-003)

**Ветка**: `070/wp-d-exclusion` | **Worktree**: `D:\Temp\claude\wt-070-exclusion` | **Агент**: Sonnet / high (Opus,
если T-D0 меняет правило) | **Сначала слиты**: ничего; **требует T-D0** | **Владеет**: строка WP-D таблицы плана.
Сущности: `data-model.md` §1–2; решения R2, R10–R12.

- [x] **T-D0** (решено 2026-11-09: О-1 и О-2 подтверждены) Оркестратор подтверждает О-1 (роли `heading`/`epigraph`/`attribution`/`dedication` вне правила
  обрывка) и О-2 (`notes_in_body` исключается). Без подтверждения О-2 — только регион; без О-1 — правило ко всем
  абзацам (тогда анти-вакуумный тест T-D3 переписывается на явное «заголовок “III” исключается — принятая цена»).

**A. Характеристика**
- [ ] **T-D1** Снимок заданий `build_editing_jobs` для `translate` и `edit` на вымышленном документе (все ключи и
  значения) — зелёный на `fdf775f`; после правки задания этих операций побайтно прежние.

**B. Падающие тесты** (`tests/test_narration_exclusion_070.py`, `tests/test_audiobook_plan.py`, нов.)
- [ ] **T-D2** Смешанный блок `audiobook`: абзацы ролей `toc_entry`, `table`, `caption`, `image`, регион `back_matter`
  (раздел `index` → `index`, иначе `apparatus`), отметка 067 (если О-2) получают свою причину, проза — `None`; блок
  `narration_include=True` и `job_kind="llm"` (падает: сегодня решение блочное, `semantic_blocks.py:1191-1208`). Блок
  из одних исключаемых → `passthrough`.
- [ ] **T-D3** Анти-вакуум (Конституция VII): заголовок главы, эпиграф, атрибуция («— Ю. Ли» с ролью `attribution`),
  короткая проза из одного предложения, заголовок перед распознанным аппаратом, начало книги до первой длинной прозы
  (регион `front_matter`) — БЕЗ причины. «(i)», «11 vv», «— 42 —» с ролью `body` — `fragment`. Граничные: ровно ½ букв
  — не обрывок; токен из трёх букв — не обрывок.
- [ ] **T-D4** Разбор payload: длина `narration_exclusion_reasons` ≠ `paragraph_ids` или неизвестная причина →
  `ValueError`; отсутствие поля → ничего не исключено.
- [ ] **T-D5** `is_marker_mode_enabled` для `audiobook` при `enable_paragraph_markers=False` и непустых ID → `True`;
  для `edit`/`translate` — как раньше.
- [ ] **T-D6** План: `send_ids`/`send_text_with_markers` — только озвучиваемые, в исходном порядке; исходные тексты по
  маркерам; `merge_audiobook_dispositions` даёт все ID в порядке, исключённые — `policy_kept_source` с исходником;
  несовпадение ID ответа с `send_ids` → `ValueError`.

**C. Реализация**
- [ ] **T-D7** `core/models.py`: словарь причин; `document/narration_exclusion.py` (нов.).
- [ ] **T-D8** `document/semantic_blocks.build_editing_jobs` (только `audiobook`): поле и `narration_include` блока.
- [ ] **T-D9** `pipeline/contracts.BlockExecutionPayload`, `pipeline/job_parsing.py` (разбор, маркеры).
- [ ] **T-D10** `pipeline/audiobook_plan.py` (нов.).

**D. Проверка**
- [ ] **T-D11** Отдельными командами: `tests/test_narration_exclusion_070.py`, `tests/test_audiobook_plan.py`,
  `tests/test_document_structure_blocks.py`, `tests/test_preparation.py`. Done: зелёные.

---

## WP-E. Чистка, эмодзи, детектор остатка, покрытие (FR-005, FR-006 детектор, FR-007 сигнал)

**Ветка**: `070/wp-e-cleanup` | **Worktree**: `D:\Temp\claude\wt-070-cleanup` | **Агент**: Sonnet / high |
**Сначала слиты**: ничего | **Владеет**: строка WP-E таблицы плана. Сущности: `data-model.md` §3; решения R1, R8, R9.

**A. Данные Unicode**
- [ ] **T-E1** `scripts/generate-unicode-emoji-data.py` (нов.): вход — локальная копия
  `https://www.unicode.org/Public/15.1.0/ucd/emoji/emoji-data.txt` (скачать один раз; путь — аргумент), выход —
  `src/docxaicorrector/text/unicode_emoji_data.py` с диапазонами и `UNICODE_EMOJI_DATA_VERSION`/`_SHA256`. Запуск под
  WSL (`bash -lc ". .venv/bin/activate && python scripts/generate-unicode-emoji-data.py <путь>"`). Done: модуль в git,
  генератор воспроизводит его байт в байт.

**B. Падающие тесты** (все файлы нов.)
- [ ] **T-E2** `tests/test_unicode_emoji_data.py`: версия = `unicodedata.unidata_version`; известные кодовые точки
  стандарта (U+1F600 `Emoji_Presentation`, U+1F3FB `Emoji_Modifier`, U+00A9 `Emoji` без presentation) — в своих
  множествах; U+2116 `№` и U+2192 `→` — не `Emoji_Presentation`.
- [ ] **T-E3** `tests/test_narration_cleanup.py` — эмодзи: ZWJ-семья, флаг, тег-флаг, keycap `1️⃣`, тон кожи,
  `❤️` (U+2764 U+FE0F) удаляются целиком; буквы, диакритика (`é`, `й`, комбинирующее ударение), кавычки «»„“,
  тире —/–, многоточие …, `[авторская вставка]`, `№`, `§`, `→`, `©`, одиночные `#`, `*`, цифры — остаются.
- [ ] **T-E4** `tests/test_narration_cleanup.py` — HTML и прочее: `<u>слово</u>`→`слово`; `слово<br/>слово`→`слово слово`;
  `<p>а</p><p>б</p>`→`а б`; `&amp;`/`&nbsp;`/`&#8212;` раскрыты; `a < b и c > d` без изменений; `<sup>2</sup>`→`2`;
  `[[DOCX_IMAGE_img_001]]` снят (О-9), `[[x]]` не тронут; `# Заголовок`→`Заголовок`; `• пункт`/`● пункт`→`пункт`;
  `1990. Год`→`1990. Год` (год не теряется, падает на старом `_NARRATION_LIST_MARKER`); `4●5` без изменений;
  `[текст](http://x.y)`→`текст`; голый `https://x.org` НЕ удаляется (О-7); идемпотентность.
- [ ] **T-E5** `tests/test_narration_residue.py`: каждый класс таблицы FR-006 ловит свою форму (вымышленные примеры) и
  молчит на чистом русском абзаце; `count` — число вхождений; «т.е.» и многоточие — не домен; «ВВП и США» — не
  `all_caps` (нет двух слов ≥ 4 букв); «II» и «Ⅳ» — римские, «I» — нет; `[serious]` — `tag_form`, `[Примеч. ред.]` — нет;
  `html_left`/`emoji_left` не входят в `REPAIRABLE_RESIDUE_CLASSES`.
- [ ] **T-E6** `tests/test_narration_coverage.py`: число словами вместо цифр не снижает долю; ответ без одного
  предложения из пяти даёт `ratio < 0.6` (анти-вакуум: правило «цифры не считаются» не прячет потерю текста); < 4
  длинных слов или < 6 токенов → `None`; основы — по `casefold`, разные падежи совпадают.

**C. Реализация**
- [ ] **T-E7** `text/narration_cleanup.py` (чистка + сканер эмодзи), `text/narration_residue.py`,
  `text/narration_coverage.py`. Без импорта `pipeline`, Streamlit, сети.

**D. Проверка**
- [ ] **T-E8** Отдельными командами четыре файла T-E2…T-E6. Done: зелёные; гард импорта (модули `text/narration_*` не
  импортируют `docxaicorrector.pipeline`).

---

## WP-F. Вызов исправления и стадия учёта (FR-006 вызов)

**Ветка**: `070/wp-f-repair` | **Worktree**: `D:\Temp\claude\wt-070-repair` | **Агент**: Sonnet / medium |
**Сначала слиты**: ничего | **Владеет**: строка WP-F таблицы плана. Сущности: `data-model.md` §4; решение R5.

**B. Падающие тесты** (`tests/test_audiobook_repair.py`, нов.)
- [ ] **T-F1** Двойник клиента Responses считает вызовы: принятый ответ — ровно 1 вызов, тексты по ID; запрос несёт только
  абзацы с остатком под маркерами и контекст ≤ 600 знаков (падает: модуля нет).
- [ ] **T-F2** Отказы: перестановка маркеров, пропуск, дубль, текст до первого маркера, пустой абзац, исключение SDK,
  `MarkerParagraphRecordLost` → `status` ≠ `accepted`, тексты прежние, причина по `data-model.md` §4; ровно 1 вызов (ни
  одного повтора).
- [ ] **T-F3** Stop до вызова → 0 вызовов, `status="skipped"`, `reason="stopped"`, `call_made=False`.
- [ ] **T-F4** Учёт: ответ двойника с `usage` (включая отвергнутый нами) попадает в `stages.audiobook_repair` снимка
  `model_accounting`; `text_generation` не меняется.
- [ ] **T-F5** События `audiobook_repair_started` / `_completed` / `_failed` с полями `contracts/events.md`, без полных
  текстов.

**C. Реализация**
- [ ] **T-F6** `pipeline/audiobook_repair.py` (через `request_text_completion`, `_build_request_kwargs`,
  `_build_marker_preserving_user_prompt`, `split_marker_preserved_paragraph_dispositions`); `STAGE_AUDIOBOOK_REPAIR` в
  `core/model_accounting.py`.

**D. Проверка**
- [ ] **T-F7** `tests/test_audiobook_repair.py`, затем `tests/test_model_accounting_069.py`. Done: зелёные.

---

## WP-B. Режим без языков и модель режима (FR-001, FR-008)

**Ветка**: `070/wp-b-language-free` | **Worktree**: `D:\Temp\claude\wt-070-language` | **Агент**: Sonnet / medium |
**Сначала слиты**: WP-A | **Владеет**: строка WP-B таблицы плана. Контракт: `contracts/audiobook-config.md`; решение R6.

**A. Характеристика**
- [ ] **T-B1** Для `translate`/`edit`: маркер подготовки, контекст вызова (языки), профиль `ui-parity-translate-*` в
  отчёте — снимок, зелёный до правки и после.

**B. Падающие тесты** (`tests/test_audiobook_language_free.py`, `tests/test_audiobook_model.py`, нов.)
- [ ] **T-B2** `language_pair_for_operation("audiobook", "en", "ru") == (None, None)`; маркер подготовки `audiobook` одинаков
  при любой паре в сессии (падает: `:sl=…:tl=…`, `processing_runtime.py:1682-1684`); `ProcessingContext` для
  `audiobook` несёт `None`.
- [ ] **T-B3** `job_changes_language(processing_operation="audiobook", …)` → `False`; шлюз качества для `audiobook` не
  включает `mixed_script`/`untranslated_*`, но общая проверка целостности работает (анти-вакуум: потеря абзаца по-прежнему
  ловится); `preserve_footnote_markers_for_block` для `audiobook` возвращает текст без изменений.
- [ ] **T-B4** `AppTest`: `translate` с выбранными языками → переключение на `audiobook`: селекторов языков нет,
  `_assess_text_transform` и рекомендации не вызываются, `app_config["source_language"]`/`["target_language"]` — `None`.
- [ ] **T-B5** Резолвер: `requested` → он; иначе `[models.audiobook].default`; без раздела — `[models.text].default`; UI и
  раннер зовут одну функцию (двойник ловит оба вызова); модель, выбранная в `edit`, не становится моделью `audiobook`.
- [ ] **T-B6** Профиль `ui-parity-standalone-audiobook` без пары; отчёт раннера хранит `null`; язык отчёта — язык UI по
  умолчанию.

**C. Реализация**
- [ ] **T-B7** `core/audiobook_mode.py` (нов.), `core/models.py:37`, `core/config.py:495-510`.
- [ ] **T-B8** `pipeline/contracts.py` (`ProcessingContext`), `pipeline/setup.py`, `pipeline/_pipeline.py`,
  `processing/processing_runtime.py`, докстринги `block_execution.py:198-234`.
- [ ] **T-B9** `ui/_ui.py`, `ui/_app.py`, локали; `validation/profiles.py`, `corpus_registry.toml`, раннер `:725`, `:6257`,
  `resources/config.toml:114-117`.

**D. Проверка**
- [ ] **T-B10** Отдельными командами: оба новых файла, `tests/test_ui.py`, `tests/test_app_preparation.py`,
  `tests/test_processing_runtime.py`, `tests/test_quality_gate_hygiene_channel_operations.py`, `tests/test_footnote_markers.py`,
  `tests/test_spec_059_translation_completeness.py`, `tests/test_real_document_validation_corpus.py`. Ручная проверка в
  браузере — `quickstart.md` §2. Done: зелёные.

---

## WP-G. Интеграция: подмножество, финализация абзацев, исправление, сборка по ID (FR-003…FR-007)

**Ветка**: `070/wp-g-integration` | **Worktree**: `D:\Temp\claude\wt-070-integration` | **Агент**: **Opus** / high |
**Сначала слиты**: WP-A, WP-B, WP-C, WP-D, WP-E, WP-F | **Владеет**: строка WP-G таблицы плана. Сущности:
`data-model.md` §5–6; решения R2, R4, R7, R8; события — `contracts/events.md`.

**A. Характеристика**
- [ ] **T-G1** Для `translate`/`edit` через обычный вход блока: DOCX/Markdown/реестр — снимок, зелёный до и после;
  `tests/test_spec_070_request_golden.py` зелёный.

**B. Падающие тесты** (`tests/test_audiobook_pass.py`, нов.; через `process_single_block` с двойником генератора)
- [ ] **T-G2** Смешанный блок: двойник генератора получает только `send_ids` (падает: сегодня весь блок); исключённые в
  DOCX — исходником, статус `policy_kept_source`; запись исключения с причиной и адресом.
- [ ] **T-G3** Пустой ответ на последней попытке → абзац звучит исходным текстом, `needs_review` `empty_answer` (падает:
  сегодня `omitted` не звучит); `source_restored` и controlled fallback — звучат с `source_restored`/`source_fallback`;
  знаменатель не уменьшается.
- [ ] **T-G4** Остаток (цифры в двух абзацах блока) → ровно один вызов исправления на блок; принятый ответ — текст в
  `.tts.txt` и DOCX; сломанный ответ → прежний текст + `needs_review` `repair_failed`; второго исправления нет; Stop перед
  исправлением → вызова нет, блок доставлен.
- [ ] **T-G5** Сборка: `.tts.txt` разбирается обратно в ожидаемые ID (`paragraph_boundary_check == "ok"`); склейка только
  `body`+`body` по форме, с парой ID; заголовок не приклеивается к прозе; модель, вернувшая Markdown-заголовок для
  `body`, не делает его заголовком (вид — из подготовки).
- [ ] **T-G6** `translate`/`edit` не строят озвучку и не держат `narration_*` состояния; события
  `audiobook_narration_exclusions`, `audiobook_needs_review`, поля `ui_audiobook_artifact_saved` — по контракту;
  удалённые события нигде не эмитятся.

**C. Реализация**
- [ ] **T-G7** `pipeline/audiobook_pass.py` (нов.): `finalize_audiobook_block`, записи, причины `needs_review`.
- [ ] **T-G8** `pipeline/block_execution.py`: подмножество в `_generate_block_chunk`, слияние, финализация вместо проекции
  (`:2482-2493`), fallback (`:2029-2060`), удаление проекции для прочих операций; `pipeline/contracts.py` (state, §5).
- [ ] **T-G9** `pipeline/narration_postprocess.py` (сборка по записям, проверка границ), `pipeline/late_phases.py`
  (события, поля, notices), `pipeline/quality_gate.py` (`build_narration_exclusion_facts`), локали.
- [ ] **T-G10** Удалить старый стриппер `generation/_generation.py:86-123`, `:533-698`; перенести
  `tests/test_narration_markdown.py` на `clean_narration_paragraph` и сборку (верные случаи — дословно); переписать
  тесты, читавшие `narration_chunks` (план §FR-007 п. 6), на реестр/записи.

**D. Проверка**
- [ ] **T-G11** Отдельными командами: `tests/test_audiobook_pass.py`, `tests/test_narration_markdown.py`,
  `tests/test_narration_exclusion_addresses.py`, `tests/test_document_pipeline.py`, `tests/test_literary_polish.py`,
  `tests/test_spec_063_apparatus_policy.py`, `tests/test_paragraph_record_and_production_verdict.py`,
  `tests/test_spec_070_request_golden.py`. Done: зелёные.

---

## WP-H. Раннер, отчёт, логирование, входы FR-009

**Ветка**: `070/wp-h-runner` | **Worktree**: `D:\Temp\claude\wt-070-runner` | **Агент**: Sonnet / medium |
**Сначала слиты**: WP-G; **требует T-H0** | **Владеет**: строка WP-H таблицы плана.

- [x] **T-H0** (решено 2026-11-09 оркестратором по прецеденту исходных книг: коммитить) Владелец решает: коммитить переводы `tests/sources/translated/*.docx` (план предлагает да) или
  `.gitignore` (research R13).
- [ ] **T-H1** Падающий тест: отчёт раннера на синтетическом логе несёт поля `data-model.md` §6, исключения и
  `needs_review` из своих событий, цену стадий `text_generation` и `audiobook_repair` отдельными строками; «не сообщено» ≠
  ноль.
- [ ] **T-H2** Падающий тест: `_SPEC_070_LOG_EVENTS` (каждое событие `contracts/events.md` эмитится в `src/` и
  зарегистрировано в документе логирования); удалённые события не эмитятся нигде; `_list_log_events.py` сканирует
  `pipeline/audiobook_repair.py`, `pipeline/audiobook_pass.py`, `core/audiobook_mode.py`.
- [ ] **T-H3** Раннер (`_extract_narration_artifact_record`, кортеж `:5000-5017`, summary), документ логирования (§3.3,
  §3.8, §5.5, новый §3.11, Changelog), `scripts/_list_log_events.py`.
- [ ] **T-H4** `scripts/measure-narration-exclusion.py`: `--operation audiobook --per-paragraph` — адреса и причины
  исключений, LLM-free (тест: на вымышленном DOCX выдаёт ожидаемые причины без клиента).
- [ ] **T-H5** Документные профили FR-009 (`contracts/audiobook-config.md` §4) и входы (по T-H0); `docs/WORKFLOW_AND_IMAGE_MODES.md`
  и `README.md` — описание нового режима.
- [ ] **T-H6** Отдельными командами: `tests/test_real_document_pipeline_validation.py`,
  `tests/test_real_document_validation_corpus.py`, `tests/test_script_contract_static.py`, `tests/test_documentation_links.py`.
  Done: зелёные.

---

## Приёмка (оркестратор)

- [ ] **T-Z1** Порядок слияния в `070/integration`: A, затем C, D, E, F; B; G; H. Каждый перенос — на свежую
  интеграционную ветку; конфликт в `TEST_TIER_INVENTORY.md` — объединение сторон.
- [ ] **T-Z2** После КАЖДОГО слияния — полный прогон в ГЛАВНОМ дереве:
  `wsl.exe -d Debian --cd "D:\Work\Projects\DocxAICorrector" -- bash scripts/test.sh tests/ -q`; перед «всё зелёное» —
  `git status --porcelain` пуст, `git diff --check` чист. Оборванный вывод — сузить, не запускать второй прогон параллельно.
- [ ] **T-Z3** Гарды в главном дереве, каждый отдельной командой: `tests/test_spec_status_consistency.py`,
  `tests/test_where_we_are_freshness.py`, `tests/test_documentation_links.py`,
  `tests/test_prompts_carry_no_corpus_literals.py`, `tests/test_config_keys_are_read.py`, `tests/test_typecheck.py`
  (≥ 180 с; новых ошибок относительно базовой линии нет).
- [ ] **T-Z4** Расширенное ревью Codex `gpt-6-astra`, `--sandbox read-only`, по рецепту AGENTS.md («Обязательная приёмка
  оркестратора») ДО слияния в `main`: самый свежий `codex.exe` (`Sort-Object LastWriteTime -Descending`), промпт файлом
  через stdin, ответ в файл, в фоне. Объём — все затронутые поверхности: модули с изменённым hunk целиком, прямые
  вызывающие/вызываемые, их тесты (список из `git diff --stat fdf775f..<head>`); в промпте — base/head SHA, команды
  `git diff --stat` и `git log --oneline`, литеральные абсолютные пути, путь к спеке и плану, отдельным абзацем что
  измерено оператором (WSL ему закрыт); требовать `file:line`, частоту и чем измерена, уверенность, вердикт последней
  строкой из фиксированного набора; формулировки без «атакуй/сломай». Каждую находку проверить по коду и приземлить
  (правка с тестом / Changelog / Non-goals). Отчёт — `docs/reviews/CODEX_REVIEW_070_<YYYY-MM-DD>.md`.
- [ ] **T-Z5** После правок по ревью — снова T-Z2/T-Z3; слияние `070/integration` в `main`, push. Спека не объявляется
  закрытой до WP-I.

## WP-I. Замер FR-009 (оркестратор, платно)

- [ ] **T-I1** [?] Согласие владельца на сумму (бюджет спеки ≈ 1 $).
- [ ] **T-I2** Snapshot исключений до прогона (`quickstart.md` §6.1): прочитать каждый `fragment` и начало каждой главы
  (заголовок, эпиграф, атрибуция без причины).
- [ ] **T-I3** Три прогона канонического раннера (`quickstart.md` §6.2). При падении — свежий run report, `failed_checks`
  дословно с `actual`/`threshold`, только потом гипотезы.
- [ ] **T-I4** Читать по таблице `quickstart.md` §6.3: SC-001…SC-003, SC-005; выборка 30 абзацев на главу против входа;
  каждый `needs_review` с `residue` объяснён. Результаты — в Changelog спеки как есть (неудача критерия фиксируется, не
  ретушируется). Прослушивание трёх глав — шаг владельца.
