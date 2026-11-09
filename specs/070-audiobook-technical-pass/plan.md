# Implementation Plan: аудиокнига — технический проход по готовому тексту

**Branch**: `070/integration` (интеграционная; рабочие ветки пакетов — `070/wp-<буква>-<slug>`) | **Date**: 2026-11-09 |
**Spec**: [spec.md](spec.md)

**Input**: `specs/070-audiobook-technical-pass/spec.md` (после правок по ревью Codex,
`docs/reviews/CODEX_REVIEW_070_SPEC_2026-11-09.md`); решения — [research.md](research.md); сущности —
[data-model.md](data-model.md); контракты — [contracts/](contracts/); проверка — [quickstart.md](quickstart.md); задачи —
[tasks.md](tasks.md).

**База**: `main` @ `fdf775f` — это `37297c4` плюс слитая ветка спеки 062 (`062/mode-defaults`: `ui/_ui.py`, `ui/_app.py`,
`core/config.py`, `core/config_loader_layers.py`, `core/config_model_registry.py`, `validation/profiles.py`,
`resources/config.toml`). **Точка ребейза** — `fdf775f`: интеграционная ветка 070 создаётся от него (или от более
свежего `main`, тогда ссылки `file:line` перепроверяются, Конституция VIII). Все ссылки ниже сверены на `fdf775f`;
ссылки спеки и ревью Codex на файлы 062 сделаны на `53ddeec` и сдвинуты (research, вступление).

## Summary

Операция `audiobook` становится одноязычным техническим проходом по готовому тексту. Второй проход «подготовить для
ElevenLabs» в переводе и редактуре удаляется целиком вместе с тегами интонации и мёртвыми правилами обзора (FR-002, D-3).
Режим перестаёт знать пару языков: ветвь до нормализации в UI, подготовке, контракте вызова, промпте, профилях и отчёте
(FR-001); модель — по одному резолверу `[models.audiobook]` → `[models.text]` для UI и раннера (FR-008). Решение «что не
звучит» принимается по абзацу на документном слое (роль, регион, форма «обрывка»), и модели отправляется только
подмножество абзацев блока (FR-003). Свой системный шаблон без правил разметки и интенсивности; переводу и редактуре
байты запросов закреплены золотыми тестами (FR-004, SC-004). После ответа — детерминированная чистка однозначного
(HTML, эмодзи по UTS #51, украшения) (FR-005), детектор остатка по классам Unicode и ОДИН вызов исправления на блок со
стадией учёта `audiobook_repair` (FR-006); `.tts.txt` собирается по ID абзацев с ролью из подготовки, склейки —
детерминированные и с адресами, плюс сигнал покрытия по абзацу (FR-007). Девять пакетов: пять параллельны с первого дня.

## Technical Context

**Language/Version**: Python 3.13.5 (WSL Debian, `.venv/bin/python`; `unicodedata.unidata_version == "15.1.0"`);
Streamlit 1.64.0.

**Primary Dependencies**: `openai` SDK (Responses + Chat Completions через OpenRouter), `anthropic` SDK, Streamlit;
**новых зависимостей нет** — данные Unicode Emoji 15.1.0 вендорятся сгенерированным модулем (research R1).

**Storage**: новых семей `.run/` нет; результат — `.run/ui_results/<stem>.result.{tts.txt,md,docx}` как сейчас;
отчёт раннера — `tests/artifacts/real_document_pipeline/runs/<run_id>/`.

**Testing**: pytest через `bash scripts/test.sh` под WSL (канонический путь AGENTS.md); Streamlit `AppTest` для UI;
платный замер — `scripts/run-real-document-validation.sh` (FR-009, после согласия владельца).

**Target Platform**: WSL Debian (`/mnt/d/Work/Projects/DocxAICorrector`), UI Streamlit локально.

**Project Type**: одно Python-приложение (`src/docxaicorrector/`), тесты в `tests/`.

**Performance Goals**: исключение и чистка — линейные проходы по тексту, без сети; исправление — не больше одного вызова
на блок с остатком (на главе — единицы вызовов; цена — SC-005, замер FR-009).

**Constraints**: `translate`/`edit` — побайтно прежние системные промпты, аргументы промпта и запросы блока (SC-004),
кроме исчезнувшего второго прохода; никаких словарей слов и литералов книг ни в коде, ни в тестах (VII); квадратные
скобки с текстом кодом не удаляются (Anti-regression 5); озвучка не блокирует доставку (Anti-regression 2).

**Scale/Scope**: книги 0,5 млн символов, 230–300 блоков; ≈ 35 файлов продукта (из них ≈ 20 — удаление FR-002),
≈ 12 новых тестовых файлов.

Неизвестных `NEEDS CLARIFICATION` нет; три развилки вынесены на подтверждение оркестратора (О-1, О-2 — задача T-D0;
R13 — T-H0); то, что определяется только данными, — в разделе «Что не определено».

## Constitution Check

### До дизайна

- **I/II — PASS.** Все проверки — `scripts/test.sh` через `wsl.exe -d Debian`; замер — канонический раннер; снимок
  исключений — `scripts/run-structural-preparation-diagnostic.sh` и `scripts/measure-narration-exclusion.py` под WSL.
- **III — PASS, полный цикл.** Удаляется контракт (второй проход и его ось конфига), появляются новые контракты
  (исправление, причина исключения, запись абзаца озвучки), меняются UI, конфиг, конвейер и промпты в порядке, который
  важен — критерий полного цикла.
- **IV — PASS.** План опирается на код `fdf775f` и сохранённые прогоны главы с их пределами (Codex 10); новых гипотез о
  реальных документах без данных нет — FR-009 проверяет.
- **V — PASS.** События, notices и поля отчёта — `contracts/events.md`; документ логирования обновляет WP-H; удалённые
  события записываются как удалённые.
- **VI — PASS.** Каждый пакет владеет перечнем файлов; правки вне перечня запрещены; DOCX аудиокниги сохранён (R4), а
  не перестроен.
- **VII — PASS с обязательствами.** Исключение — роль, регион, форма; детектор и чистка — категории и свойства Unicode
  закреплённой версии (R1); ни одного словаря слов (транслитерации, «ё», чисел — Non-goals). Правила, которые ВЫЧИТАЮТ
  из знаменателя (FR-003 «обрывок», роли-исключения О-1) и из сигнала потери (цифры в покрытии), несут анти-вакуумные
  тесты: эпиграф, атрибуция, заголовок, короткая проза не исключаются; абзац с выпавшим предложением даёт низкое
  покрытие. Сборка по роли подготовки, а не по форме текста — «no source signal, no repair».
- **VIII — PASS.** Ссылки сверены 2026-11-09 на `fdf775f`; расхождения со спекой (сдвиг строк файлов 062, `ui/_app.py:432`)
  записаны («Дефекты спеки»).

### После дизайна

PASS. Отклонения от спеки (ниже) — уточнения, разрешающие противоречия внутри спеки или её пробелы; О-1 и О-2 требуют
подтверждения оркестратора до WP-D. Нарушений, требующих Complexity Tracking, нет.

## Project Structure

### Документация (эта спека)

```text
specs/070-audiobook-technical-pass/
├── spec.md
├── plan.md                 # этот файл
├── research.md             # решения R1–R13
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── prompts.md          # системный шаблон аудиокниги, промпт режима, пример, промпт исправления
│   ├── events.md           # события, notices, поля отчёта
│   └── audiobook-config.md # ключи, резолвер модели, пара языков, профили
└── tasks.md
```

### Исходный код (затронуто / создано)

```text
src/docxaicorrector/
├── core/
│   ├── models.py                      # WP-B: LANGUAGE_CHANGING_OPERATIONS={"translate"}; WP-D: NARRATION_EXCLUSION_*
│   ├── audiobook_mode.py              # НОВЫЙ WP-B: resolve_audiobook_model, language_pair_for_operation
│   ├── config.py                      # WP-A: поле audiobook_postprocess_default; WP-C: ветвь audiobook в load_system_prompt;
│   │                                  #       WP-B: «auto» только для translate в _validate_text_transform_context
│   ├── config_loader_layers.py        # WP-A
│   ├── config_runtime_sections.py     # WP-A
│   └── model_accounting.py            # WP-F: STAGE_AUDIOBOOK_REPAIR
├── document/
│   ├── semantic_blocks.py             # WP-D: narration_exclusion_reasons (только audiobook), narration_include блока
│   └── narration_exclusion.py         # НОВЫЙ WP-D: причина исключения, правило обрывка
├── text/
│   ├── narration_cleanup.py           # НОВЫЙ WP-E: FR-005 + сканер эмодзи
│   ├── unicode_emoji_data.py          # НОВЫЙ WP-E: сгенерирован из emoji-data.txt 15.1.0
│   ├── narration_residue.py           # НОВЫЙ WP-E: классы FR-006
│   └── narration_coverage.py          # НОВЫЙ WP-E: сигнал покрытия FR-007
├── generation/_generation.py          # WP-G: удаление старого стриппера narration (:86-123, :533-698)
├── pipeline/
│   ├── audiobook_plan.py              # НОВЫЙ WP-D: план блока, слияние disposition
│   ├── audiobook_repair.py            # НОВЫЙ WP-F: один вызов исправления
│   ├── audiobook_pass.py              # НОВЫЙ WP-G: обработка абзацев блока, записи, needs_review
│   ├── block_execution.py             # WP-B (докстринги/язык), WP-G (подмножество, финализация блока, fallback)
│   ├── job_parsing.py                 # WP-D: разбор narration_exclusion_reasons; маркеры всегда для audiobook
│   ├── contracts.py                   # WP-A (state shortfall), WP-D (payload), WP-B (ProcessingContext языки), WP-G (state)
│   ├── narration_postprocess.py       # WP-A (удаление второго прохода, тегов, мёртвых правил), WP-G (сборка по ID)
│   ├── late_phases.py                 # WP-A (ошибки/метки второго прохода), WP-G (публикация новых счётчиков)
│   ├── quality_gate.py                # WP-G: build_narration_exclusion_facts без семей потерь
│   ├── setup.py, _pipeline.py         # WP-B: пара языков
│   ├── support.py                     # WP-C: аргументы промпта для audiobook
│   └── text_call_support.py           # WP-A: комментарий
├── processing/processing_runtime.py   # WP-A (поле результата), WP-B (маркер подготовки, старт)
├── runtime/state.py                   # WP-A
├── ui/_ui.py, ui/_app.py              # WP-A (флажок, кортеж, подписи), WP-B (языки, оценка, модель)
├── ui/locales/ru.json, en.json        # WP-A, WP-B, WP-G
├── validation/profiles.py             # WP-A (поле), WP-B (языки, модель)
└── resources/
    ├── config.toml                    # WP-A (комментарий :114-117 переписывает WP-B)
    └── prompts/
        ├── system_prompt_audiobook.txt        # НОВЫЙ WP-C
        ├── operation_audiobook.txt            # WP-C (переписан)
        ├── example_audiobook.txt              # WP-C (переписан)
        └── operation_audiobook_repair.txt     # НОВЫЙ WP-C
corpus_registry.toml                           # WP-A (удаление), WP-B (standalone без пары), WP-H (профили FR-009)
tests/artifacts/real_document_pipeline/run_lietaer_validation.py   # WP-A, WP-B, WP-H
scripts/generate-unicode-emoji-data.py         # НОВЫЙ WP-E (инструмент разработчика)
scripts/measure-narration-exclusion.py         # WP-H: поабзацный режим для audiobook
scripts/_list_log_events.py                    # WP-H: новые модули
docs/LOGGING_AND_ARTIFACT_RETENTION.md, README.md, docs/RUNNING_THE_PIPELINE.md,
docs/WORKFLOW_AND_IMAGE_MODES.md, docs/testing/REAL_DOCUMENT_VALIDATION_WORKFLOW.md        # WP-A (удаление), WP-H (новое)
docs/testing/TEST_TIER_INVENTORY.md            # каждый пакет — свои новые файлы (`## Unit-Contract`)
```

**Structure Decision**: новые чистые модули кладутся по слою: `document/` — решение по роли и региону, `text/` —
чистые функции над текстом (без конвейера и сети; это и делает WP-E параллельным), `pipeline/` — исполнение, `core/` —
резолвер режима. `pipeline/audiobook_plan.py` и `pipeline/audiobook_repair.py` не импортируют Streamlit и
`block_execution` — их можно строить и тестировать до интеграции.

---

## Дизайн по требованиям

### FR-002 — удаление второго прохода (WP-A)

Удаляется всё по таблице FR-002 ревью Codex, строки сверить на `fdf775f`:
- `pipeline/narration_postprocess.py`: `_project_final_cleanup_narration_chunks` (`:85-167`), ветвь второго прохода в
  `_build_narration_text` (`:174-190`), `_should_run_audiobook_postprocess` (`:281`), `_resolve_audiobook_postprocess_model`
  (`:291`), `_resolve_audiobook_postprocess_chunk_size` (`:296`), `_build_narration_postprocess_groups` (`:304`),
  `_count_narration_paragraphs` и `_NARRATION_PARAGRAPH_BREAK_PATTERN` (`:352`, `:82`),
  `_record_postprocess_paragraph_shortfall` (`:356`), `_run_audiobook_postprocess` (`:411-533`). **Остаются**
  `_collect_narration_chunks` (`:287`; его заменит WP-G), `_assemble_narration_recording_joins`, обзор.
- Теги (D-3, кодовая сторона): `_ELEVENLABS_TAG_PATTERN`, `_NARRATION_ANY_TAG_PATTERN` (`:43-44`), ветвь
  `disallowed_tags` (`:237-254`), `tag_count` в `ui_audiobook_artifact_saved` (`late_phases.py:1635`).
- Мёртвые правила обзора (FR-006, последнее предложение): `internal_placeholder`, `raw_url`, `markdown_heading`
  (`:46-47`, `:73`). Счётчик правила — число вхождений (так у оставшихся уже есть, `:224-230`).
- `pipeline/late_phases.py`: реэкспорты (`:37-49`), ошибки второго прохода (`:1155-1200`, события
  `audiobook_postprocess_failed*`), метки `narration_mode` (`:1280`, `:1364`, `:1637`), notice shortfall (`:1336-1352`),
  поля `postprocess_*` (`:1660-1666`), `audiobook_postprocess_enabled` результата (`:1725`). Обработка ошибок самой
  аудиокниги (сборка narration) сохраняется.
- `pipeline/contracts.py:306-312`; конфиг (`core/config.py:272`, `core/config_loader_layers.py:180`,
  `core/config_runtime_sections.py:528`, `:574-576`, `:603`) и env; `runtime/state.py` (снимок, getter, setter, init/reset —
  `:65`, `:95`, `:152`, `:416`, `:426`, `:626`, `:754` по Codex, сверить); `processing/processing_runtime.py` (`:31`,
  `:1695`, `:1723`, `:1821`, `:2182`); UI (`ui/_ui.py:95-114` подписи, `:791-799` флажок, кортеж `render_sidebar`
  `:717` — с 13 до 12 элементов, аргументы рендера `:1054`, `:1157`; `ui/_app.py:911`, `:1029`, `:1050`); локали; профили
  (`validation/profiles.py:105`, `:164`, `:190`, `:285`, `:317-322`, `:374`, `:456`, `:588`); `corpus_registry.toml`
  (профиль `:151-160` и поле во всех профилях); раннер (`run_lietaer_validation.py:5014-5016` и извлечение `:5020-5030`);
  комментарии `block_execution.py:1764-1766`, `text_call_support.py:4`; документы (перечень FR-002 спеки); тесты (перечень
  Codex).
- **Перевод и редактура не пишут `.tts.txt`**: без второго прохода `_build_narration_text` для них возвращает `None`
  (`:174-176`) — тест на это (SC-004).
- Старый ключ → `config_key_ignored`: тест загрузки пользовательского `config.toml` с `audiobook_postprocess_default =
  true` (механизм `core/config.py:1122`). `tests/test_config_keys_are_read.py` (`:23`, исключения `:68-79`) — без новых
  исключений.
- Исторические спеки, ревью и сохранённые сводки не трогаются; в действующих спеках (054, 061) — запись в Changelog о
  замене поведения (оркестратор при слиянии).

### FR-001, FR-008 — режим без языков и модель режима (WP-B)

Контракт — `contracts/audiobook-config.md`.
- `core/models.py:37`: `LANGUAGE_CHANGING_OPERATIONS = frozenset({"translate"})`. Потребители (`block_execution.py:236`,
  `:1531`, `quality_gate.py:1654`, `:2727`, `narration_postprocess.py:97` — последний удаляет WP-A) получают правильный
  ответ без правок кода; тесты закрепляют: для `audiobook` `job_changes_language` → `False`, языковые детекторы шлюза
  (`mixed_script`, `untranslated_*`) не включаются, общая проверка целостности — включается.
- `core/audiobook_mode.py`: `language_pair_for_operation` и `resolve_audiobook_model` (research R6). Пара для
  `audiobook` — `(None, None)` во всех точках: `ui/_app.py:1047-1049`, `processing_runtime.py:1678` (маркер подготовки
  без суффикса языков для `audiobook`; кеш подготовки не зависит от оставшейся в сессии пары), `:2090-2092`,
  `pipeline/setup.py:174-175`, `pipeline/_pipeline.py:989-990`, `pipeline/contracts.py:246-247` (`str | None`),
  `validation/profiles.py:314-315`, раннер `:6257-6258` (передаёт `None`), `:725` (язык отчёта — язык UI по умолчанию).
- UI: для `audiobook` селекторы «Целевой язык»/«Язык оригинала» не рисуются (`ui/_ui.py:762-790`; сейчас целевой
  рисуется всегда, исходный — для `{translate, audiobook}`, `:775`), значения языков не читаются из сессии;
  `_assess_text_transform` и `_maybe_apply_file_recommendations` (`ui/_app.py:1311-1321`) для `audiobook` не вызываются;
  модель — R6 (свой «последний выбор»).
- `core/config.py:495-510` (`_validate_text_transform_context`): `auto` разрешён только для `translate` (ветвь
  `audiobook` до него не доходит — R3).
- Глоссарий и контекст книги не подключаются (`pipeline/support.py:21`, `pipeline/glossary_phase.py:121` — уже только
  translate; тест закрепляет). Сноски: `pipeline/footnote_markers.py:355-356` — тест «для `audiobook` маркеры сносок не
  восстанавливаются» после смены множества.
- `corpus_registry.toml:175-182`: `ui-parity-standalone-audiobook` без пары.
- Модель: `validation/profiles.py:309` для `audiobook` → резолвер; комментарий `resources/config.toml:114-117`.

### FR-004, SC-004 — промпт и золотые запросы (WP-C)

Контракт — `contracts/prompts.md`, решение — research R3. Сначала (T-C1) на `fdf775f` записываются хеши матрицы
`load_system_prompt` и словари `build_system_prompt_arguments` для `translate`/`edit`; затем ветвь `audiobook`, новые
файлы промптов, аргументы для `audiobook` в `pipeline/support.py:26-45`. Тесты `tests/test_config.py:917-1002` (наличие
фраз) удаляются, их место — тесты сборки `tests/test_audiobook_prompt.py` (свойства §0 контракта). Случай `audiobook`
золотого теста 069 (`tests/test_generation_request_profile.py`) меняется намеренно; случаи `translate`/`edit` — нет.
Вариант `repair` — тот же загрузчик (`prompt_variant="repair"`).

### FR-003 — что не звучит (WP-D; подключение — WP-G)

Решение — research R2, R10, R11, R12; сущности — `data-model.md` §1–2.
- `document/narration_exclusion.py`: `resolve_narration_exclusion_reason(*, structural_role, region, back_matter_section,
  in_notes_in_body, text) -> str | None` (чистая) и `is_fragment_without_connected_text(text)`.
- `document/semantic_blocks.build_editing_jobs` (`:274`): только для `audiobook` — поле `narration_exclusion_reasons`;
  `narration_include` блока = есть абзац без причины (заменяет для `audiobook` вызов `_resolve_narration_include`,
  `:325-330`; для прочих операций — без изменений).
- `pipeline/contracts.BlockExecutionPayload` (`:379`) + `pipeline/job_parsing.py` (разбор, проверка длины и словаря);
  `job_parsing.is_marker_mode_enabled` (`:189`) — для `audiobook` всегда по наличию ID (О-3).
- `pipeline/audiobook_plan.py`: `build_audiobook_block_plan`, `merge_audiobook_dispositions` (исключённые →
  `policy_kept_source` с исходным текстом).
- Подключение в `_generate_block_chunk` и после генерации — WP-G (один владелец `block_execution.py` в волне 3).

### FR-005, FR-006 (детектор), FR-007 (покрытие) — чистые функции (WP-E)

Research R1, R8, R9; сущности — `data-model.md` §3. Всё — без конвейера: `text/narration_cleanup.py`,
`text/unicode_emoji_data.py` (+ генератор), `text/narration_residue.py`, `text/narration_coverage.py`.

### FR-006 (вызов) — исправление (WP-F)

Research R5; сущности — `data-model.md` §4. `pipeline/audiobook_repair.py::repair_block_residue` получает готовый
системный промпт и список `RepairItem` — от промпта WP-C и детектора WP-E не зависит (интерфейс задан здесь);
`core/model_accounting.py`: `STAGE_AUDIOBOOK_REPAIR`.

### FR-007 и интеграция (WP-G)

Порядок обработки блока `audiobook` в `process_single_block` (`block_execution.py:2280`):
1. `plan = build_audiobook_block_plan(payload)`; ID `plan.send_ids` дописываются в
   `state.narration_expected_paragraph_ids`, исключения — в `state.narration_exclusions` (до вызова модели —
   стабильный знаменатель, Codex «Оставшиеся критерии»).
2. `_generate_block_chunk` (`:1235`) для `audiobook` отправляет подмножество (`:1283`, `:1287` → `plan.*`);
   `merge_audiobook_dispositions` возвращает текст блока по всем ID.
3. Классификация, аппарат, сноски — как сейчас (сноски для `audiobook` пропускаются, `footnote_markers.py:355`).
4. **Вместо проекции озвучки** (`:2482-2493`) — `pipeline/audiobook_pass.finalize_audiobook_block(...)`: для каждого
   `send_id` — текст по статусу (R7), `clean_narration_paragraph`, `detect_narration_residue`; абзацы блока с
   исправляемым остатком → один `repair_block_residue`; повтор чистки, детектора, `paragraph_coverage`; записи
   `NarrationParagraphRecord` в `state.narration_paragraphs`; текст disposition заменяется итоговым (DOCX и Markdown
   несут текст озвучки, R4) — блок пересобирается через `MarkerPreservedBlockText` (запись не теряется,
   `_generation.py:360-394`).
5. Controlled fallback (`continue_controlled_processed_block_rejection`, `:2029-2060`): для `audiobook` — тот же
   `finalize_audiobook_block` над исходными текстами с причиной `source_fallback` (R7).
6. `state.narration_chunks`, проекция озвучки для прочих операций и семьи потерь удаляются (R7); тесты, читавшие
   `narration_chunks` (`test_block_execution_passthrough_bypass`, `test_document_pipeline`, `test_footnote_markers`,
   `test_literary_polish`, `test_paragraph_record_and_production_verdict`, `test_spec_059_translation_completeness`,
   `test_spec_063_apparatus_policy`), переписываются на реестр/записи — проверяемое ими свойство сохраняется.
7. Сборка (`narration_postprocess._build_narration_text`, `:170-194`): тексты записей через `"\n\n"`, склейка по роли и
   форме (R8) с парами ID; проверка границ — разбор итогового текста обратно в записи (`paragraph_boundary_check`;
   несовпадение — ERROR `audiobook_paragraph_boundary_mismatch`, доставка не блокируется, Anti-regression 2).
8. `late_phases`: события `audiobook_narration_exclusions`, `audiobook_needs_review`, новые поля
   `ui_audiobook_artifact_saved` (`contracts/events.md`), notices.
9. Удаление старого стриппера в `generation/_generation.py` (`:86-123`, `:533-698`) и перенос
   `tests/test_narration_markdown.py`.

### FR-009 — замер (WP-H готовит, WP-I выполняет)

WP-H: документные профили и входы (R13), поабзацный режим `scripts/measure-narration-exclusion.py` (адреса исключений до
прогона), раннер и отчёт по `contracts/events.md`, документ логирования. WP-I — оркестратор, платно, после приёмки и
согласия владельца: `quickstart.md` §6.

---

## Отклонения от спеки

Каждое — уточнение, разрешающее противоречие или пробел спеки; ни одно не ослабляет проверку.

- **О-1. Правило обрывка не применяется к ролям `heading`, `epigraph`, `attribution`, `dedication` (FR-003).** Спека
  требует одновременно правило «нет токена ≥ 3 букв или букв < ½» во всём документе и «заголовки, эпиграфы и атрибуции
  озвучиваются»; буквально это исключает заголовок «III»/«1» и атрибуцию «— Ю. Ли». Роль — сигнал подготовки
  (Конституция VII). Цена — OCR-мусор с ролью `heading` звучит (виден детектору, читается в SC-001). **Требует
  подтверждения оркестратора (T-D0).**
- **О-2. Абзацы-примечания в теле (отметка 067 FR-001) исключаются с причиной `notes_in_body` (FR-003).** FR-003
  говорит «аппарат по региону, как сейчас», User Story 1 — «без справочного аппарата»; отметка — уже распознанный
  аппарат. **Требует подтверждения оркестратора (T-D0)**; без него — только регион.
- **О-3. Аудиокнига всегда в режиме маркеров** (research R12): без ID нет FR-007.
- **О-4. Набор файлов результата не меняется** (research R4): DOCX/MD несут текст озвучки и исключённые абзацы как
  есть. Спека об этом молчит.
- **О-5. Семьи потерь озвучки удаляются** (research R7): `omitted`, `source_restored`, controlled fallback озвучиваются
  исходным текстом с `needs_review` — так велят Edge Cases; их счётчики и события теряют производителя.
- **О-6. Селектор модели аудиокниги остаётся, со своим «последним выбором»** (research R6): «явная модель UI» FR-008
  иначе неотличима от модели, оставшейся от редактуры.
- **О-7. Сырой URL кодом не удаляется** (research R8): FR-005 — «всё прочее переписывает модель», FR-006 — класс «URL и
  домены»; сегодняшнее удаление (`_generation.py:604`) делало этот класс недостижимым, как и мёртвое правило `raw_url`.
- **О-8. Числа сигнала покрытия** (длинное слово ≥ 6 букв, основа 5, минимум 4 длинных слова и 6 токенов, порог 0,6) —
  предварительные, из измерителя раздела «Что измерено» (research R9); FR-009 читает каждое срабатывание.
- **О-9. Внутренние токены конвейера `[[DOCX_<KIND>_…]]` снимаются кодом.** Anti-regression 5 разрешает удалять из
  квадратных скобок только разобранные маркеры `[[DOCX_PARA_…]]`; плейсхолдер картинки внутри текстового абзаца
  (`[[DOCX_IMAGE_…]]`, сегодня его снимает `_generation.py:562`) по букве остался бы и был бы прочитан. Это синтаксис
  конвейера, не авторский текст; план читает Anti-regression 5 как «кроме токенов конвейера `[[DOCX_*]]`».

## Дефекты спеки, найденные при планировании (спеку не правлю — для оркестратора)

1. `spec.md:113-114` (FR-001) — `ui/_app.py:432` назван местом, где «подготовка и её кеш зависят от пары». На `fdf775f`
   (и на `53ddeec`) это ключ оценки цены режимов ПЕРЕВОДА (`_refresh_translation_cost_estimates`, `ui/_app.py:398-436`),
   для `audiobook` не исполняется. Зависимость подготовки от пары — `processing_runtime.py:1678` через вызовы
   `ui/_app.py:1152`, `:1203`.
2. `spec.md:147-149` (FR-003) — правило обрывка противоречит «заголовки, эпиграфы и атрибуции озвучиваются» на
   заголовках-числах и двухбуквенных атрибуциях (О-1).
3. `spec.md:141-143` (FR-003) — не назван аппарат, оставленный импортом в теле (067 FR-001), хотя User Story 1 его
   исключает (О-2).
4. `spec.md:265` (Anti-regression 5) — запрещает снимать `[[DOCX_IMAGE_…]]` и прочие токены конвейера (О-9).
5. `spec.md:99-101` (Edge Cases) — не сказано, что делать с controlled fallback блока (весь блок — исходник) в
   аудиокниге; план: озвучивать с `needs_review` `source_fallback` (О-5).
6. `spec.md:207-209` (FR-008) — «явная модель UI» не определена при селекторе, у которого всегда есть значение и общий
   с редактурой «последний выбор» (О-6).
7. `spec.md:210-213` (FR-009) — для переведённых входов нет документных профилей; гард корпуса требует путь под
   `tests/sources/` (`tests/test_real_document_validation_corpus.py:88-90`) — решение о коммите переводов (R13, T-H0).
8. Ссылки спеки на файлы 062 (`core/config.py:1704`, `:1721-1771`, `:1754`; `ui/_ui.py:728-753`, `:781`;
   `validation/profiles.py:304`, `:310`) сделаны на `53ddeec` и после слияния 062 сдвинуты (`core/config.py:1751-1820`,
   `ui/_ui.py:762-790`, `:814-830`, `validation/profiles.py:309`, `:314-315`). Не ошибка, но агентам — сверять по плану.

---

## Порядок реализации: пакеты работ

Каждый пакет — отдельная ветка в отдельном боковом worktree вне репозитория (`D:\Temp\claude\wt-070-<slug>`, `.venv` —
симлинком; AGENTS.md «Боковые worktree»). Тесты истории (`test_spec_status_consistency`) — только в главном дереве.
Каждый пакет начинает с характеристических тестов того, что должно остаться прежним, затем падающие тесты нового
поведения (анти-вакуум), затем код. Агенты — по правилу владельца: Haiku механика, Sonnet ограниченная инженерия, Opus —
правила конвейера уровня спеки.

| Пакет | Объём | Агент / усилие | Владеет файлами | Доказывающие тесты (анти-вакуум) | Зависит от |
|---|---|---|---|---|---|
| **WP-A** Удаление второго прохода, тегов и мёртвых правил (FR-002, D-3 код, FR-006 последнее предложение) | большой, механический | Sonnet / medium (документы — можно Haiku) | `pipeline/narration_postprocess.py`, `pipeline/late_phases.py`, `pipeline/contracts.py` (только `:306-312`), `pipeline/text_call_support.py`, `pipeline/block_execution.py` (только комментарий `:1764-1766`), `core/config.py` (только поле `:272`), `core/config_loader_layers.py`, `core/config_runtime_sections.py`, `runtime/state.py`, `processing/processing_runtime.py` (только поле результата), `ui/_ui.py`, `ui/_app.py` (только флажок), `ui/locales/*.json`, `validation/profiles.py` (только поле), `corpus_registry.toml`, `resources/config.toml` (комментарий), раннер (`:5000-5030`), документы FR-002, тесты по перечню Codex, `tests/test_spec_070_postpass_removed.py` (нов.) | `config_key_ignored` на старый ключ (падает, пока ключ читается); флажка нет в сайдбаре для `edit`/`translate` (`AppTest`); `translate`/`edit` не пишут `.tts.txt`; профиля `…-postprocess` нет и поля нет ни в одном профиле; `disallowed_tags`/`internal_placeholder`/`raw_url`/`markdown_heading` не публикуются; символы второго прохода не импортируются (`ImportError` на старых именах); `test_config_keys_are_read.py` без новых исключений | — (волна 1) |
| **WP-C** Системный шаблон, промпты, золотые запросы (FR-004, SC-004) | средний | Sonnet / medium | `core/config.py` (только `load_system_prompt` и константы путей), `pipeline/support.py`, `resources/prompts/{system_prompt_audiobook,operation_audiobook,example_audiobook,operation_audiobook_repair}.txt`, `tests/test_spec_070_request_golden.py` (нов.), `tests/test_audiobook_prompt.py` (нов.), `tests/test_config.py` (только удаление `:917-1002`), `tests/test_generation_request_profile.py` (только случай audiobook) | СНАЧАЛА хеши матрицы на `fdf775f` (зелёные до и после правки); свойства §0 контракта (падают на текущем шаблоне: в нём `{target_language}`, интенсивность и правила 4–7); одинаковый промпт при любых языках/интенсивности; `repair` без примера; ни литерала книг | — (волна 1) |
| **WP-D** Исключение по абзацу на документном слое и план блока (FR-003) | средний | Sonnet / high (Opus — если О-1/О-2 изменятся) | `core/models.py` (только словарь причин), `document/narration_exclusion.py` (нов.), `document/semantic_blocks.py`, `pipeline/contracts.py` (только `BlockExecutionPayload`), `pipeline/job_parsing.py`, `pipeline/audiobook_plan.py` (нов.), `tests/test_narration_exclusion_070.py` (нов.), `tests/test_audiobook_plan.py` (нов.), `tests/test_document_structure_blocks.py` (случаи audiobook) | смешанный блок: TOC/таблица/подпись/картинка/указатель/аппарат исключены по абзацу (падает: сегодня блок целиком или ничего, `semantic_blocks.py:1191-1208`); анти-вакуум: заголовок, эпиграф, атрибуция, короткая проза, заголовок перед распознанным аппаратом НЕ исключены; «(i)», «11 vv» — `fragment`; задания `translate`/`edit` побайтно прежние (снимок до правки); план: `send_ids` в порядке, слияние возвращает все ID, исключённые — `policy_kept_source` с исходником | T-D0 (решение О-1, О-2); волна 1 |
| **WP-E** Чистка, эмодзи, детектор остатка, покрытие (FR-005, FR-006 детектор, FR-007 сигнал) | средний | Sonnet / high | `text/narration_cleanup.py`, `text/unicode_emoji_data.py`, `text/narration_residue.py`, `text/narration_coverage.py` (все нов.), `scripts/generate-unicode-emoji-data.py` (нов.), `tests/test_narration_cleanup.py`, `tests/test_unicode_emoji_data.py`, `tests/test_narration_residue.py`, `tests/test_narration_coverage.py` (все нов.) | эмодзи-последовательности (ZWJ, флаги, keycaps, модификаторы, FE0F) удаляются целиком, буквы, диакритика, кавычки «» „“, тире, многоточие, `[авторская вставка]`, `№`, `→`, `©` без FE0F — остаются; `<u>слово</u>`→`слово`, `слово<br/>слово`→`слово слово`, `&amp;`→`&`, `a < b` без изменений, `<sup>2</sup>`→`2` и детектор видит цифру; `1990. …` сохраняет год; каждый класс ловит свою форму и молчит на чистом тексте; число словами не снижает покрытие, выпавшее предложение снижает; версия данных = `unicodedata.unidata_version` | — (волна 1) |
| **WP-F** Вызов исправления и стадия учёта (FR-006 вызов) | малый | Sonnet / medium | `pipeline/audiobook_repair.py` (нов.), `core/model_accounting.py` (только константа), `tests/test_audiobook_repair.py` (нов.) | ровно ОДИН вызов SDK на блок (двойник клиента считает; падает на `generate_markdown_block`); стадия `audiobook_repair` в снимке учёта, в т.ч. у принятого провайдером, но отвергнутого ответа; перестановка/пропуск/дубль маркера, пустой абзац, исключение, Stop до вызова → прежний текст и причина; Stop → вызова нет | — (волна 1) |
| **WP-B** Режим без языков и модель режима (FR-001, FR-008) | средний | Sonnet / medium | `core/models.py` (только `LANGUAGE_CHANGING_OPERATIONS`), `core/audiobook_mode.py` (нов.), `core/config.py` (только `_validate_text_transform_context`), `pipeline/contracts.py` (только `ProcessingContext`), `pipeline/setup.py`, `pipeline/_pipeline.py`, `pipeline/block_execution.py` (только докстринги `job_changes_language`), `processing/processing_runtime.py`, `ui/_ui.py`, `ui/_app.py`, `ui/locales/*.json`, `validation/profiles.py`, `corpus_registry.toml` (standalone-профиль), `resources/config.toml` (комментарий), раннер (`:725`, `:6257`), `tests/test_audiobook_language_free.py` (нов.), `tests/test_audiobook_model.py` (нов.), `tests/test_ui.py`, `tests/test_app_preparation.py`, `tests/test_processing_runtime.py`, `tests/test_real_document_validation_corpus.py`, `tests/test_quality_gate_hygiene_channel_operations.py`, `tests/test_footnote_markers.py` | язык и режим перевода из сессии не влияют на контекст, промпт и маркер подготовки (падает: сегодня `:sl=…:tl=…`); `job_changes_language("audiobook", en, ru)` → `False`; языковые детекторы шлюза выключены, целостность — нет; сноски не восстанавливаются; селекторов языков нет и оценка языка не вызывается (`AppTest`); модель: requested → `[models.audiobook]` → `[models.text]`, одна функция у UI и раннера, выбор редактуры не протекает; отчёт хранит `null` | WP-A слит (общие UI/профили/runtime/раннер) |
| **WP-G** Интеграция: подмножество, финализация абзацев, исправление, сборка по ID (FR-003 подключение, FR-005–FR-007) | большой | **Opus** / high | `pipeline/block_execution.py`, `pipeline/audiobook_pass.py` (нов.), `pipeline/narration_postprocess.py`, `pipeline/late_phases.py`, `pipeline/contracts.py` (state), `pipeline/quality_gate.py` (`build_narration_exclusion_facts`), `generation/_generation.py` (удаление стриппера), `ui/locales/*.json` (notices), `tests/test_audiobook_pass.py` (нов.), `tests/test_narration_markdown.py`, `tests/test_narration_exclusion_addresses.py`, тесты с `narration_chunks` (7 файлов, §FR-007 п. 6), `tests/test_document_pipeline.py` | через ОБЫЧНЫЙ вход блока с двойником генератора: исключённые не отправлены (двойник видит только `send_ids`) и стоят в DOCX исходником; пустой ответ → исходный текст + `needs_review` (падает: сегодня `omitted` не звучит); `source_restored`/fallback звучат с причиной; остаток → один вызов, сломанный ответ → прежний текст; Stop перед исправлением → вызова нет, блок доставлен; `.tts.txt` разбирается обратно в ожидаемые ID; склейка только `body`+`body` и с парой ID; заголовок не приклеивается к прозе; знаменатель не уменьшается пустым ответом; translate/edit не строят озвучку | A, B, C, D, E, F слиты |
| **WP-H** Раннер, отчёт, логирование, входы FR-009 | средний | Sonnet / medium | раннер, `tests/test_real_document_pipeline_validation.py`, `docs/LOGGING_AND_ARTIFACT_RETENTION.md`, `scripts/_list_log_events.py`, `scripts/measure-narration-exclusion.py`, `corpus_registry.toml` (документные профили), `tests/sources/translated/*` (по решению T-H0), `tests/test_real_document_validation_corpus.py`, `docs/WORKFLOW_AND_IMAGE_MODES.md`, `README.md` (описание нового режима) | отчёт несёт `data-model.md` §6 и цену по стадиям; `_SPEC_070_LOG_EVENTS`: каждое событие эмитится и зарегистрировано, удалённые — нигде не эмитятся; `_list_log_events.py` сканирует новые модули; профили существуют и корпус их видит; измеритель выдаёт адреса исключений без LLM | G слит; T-H0 |
| **WP-I** Замер FR-009 | — | оркестратор | данные — вне git; итог — Changelog спеки | `quickstart.md` §6 | приёмка + Codex + слияние в `main`; согласие владельца на сумму |

### Порядок слияния

```text
волна 1:  WP-A ─┐  WP-C ─┐  WP-D ─┐  WP-E ─┐  WP-F ─┐       (WP-D — после решения T-D0)
          слияние: A первым (самый широкий), затем C (core/config.py, tests/test_config.py — другие hunks),
          D (pipeline/contracts.py — другой dataclass), E, F — в любом порядке
волна 2:  WP-B  ← A
волна 3:  WP-G  ← A, B, C, D, E, F
волна 4:  WP-H  ← G
приёмка:  полный `scripts/test.sh tests/ -q` в ГЛАВНОМ дереве на `070/integration`, `git status --porcelain` пуст
          → расширенное ревью Codex по всем затронутым поверхностям → слияние в main → WP-I (платно, по согласию)
```

Общие файлы, которые пакеты трогают в разных hunks: `core/config.py` (A: поле; C: загрузчик; B: валидация),
`pipeline/contracts.py` (A: state `:306-312`; D: payload; B: `ProcessingContext`; G: state), `ui/_ui.py`/`ui/_app.py`/
`validation/profiles.py`/`processing_runtime.py`/раннер/`corpus_registry.toml` (A → B → H — строго по волнам),
`ui/locales/*.json` (A → B → G), `docs/testing/TEST_TIER_INVENTORY.md` (все — только добавляют свои строки в
`## Unit-Contract`; конфликт при слиянии решается объединением обеих сторон, гард
`test_inventory_lists_every_top_level_test_file_exactly_once`, `tests/test_script_contract_static.py:363-397`).
После КАЖДОГО переноса пакета на свежую `070/integration` — повторный полный прогон в главном дереве (AGENTS.md,
2026-08-08). Тема коммита пакета называет `spec 070`; статус спеки обновляет оркестратор вместе с первым слиянием.

## Риски

| Риск | Чем закрыт |
|---|---|
| Удаление FR-002 оставит мёртвую ветку или сломает перевод | перечень Codex + `ImportError`-тест на старые имена; SC-004 золотые хеши; полный прогон после A |
| Правило обрывка выбросит смысловой абзац | О-1; анти-вакуумные тесты D; FR-009 snapshot до прогона и чтение каждого `fragment` |
| Модель вернёт Markdown/теги вопреки промпту | чистка R8 снимает синтаксис; детектор `tag_form`/`html_left` видит остаток |
| Исправление тратит больше одного вызова | двойник SDK в WP-F считает вызовы; путь `request_text_completion` без повторов (R5) |
| Двойная стоимость при отказе Responses и переходе на Chat | это отказ без генерации; учёт стадии по ответу провайдера; FR-009 читает `stages.audiobook_repair.model_call_count` |
| Сборка по ID расходится с текстом `.tts.txt` | `paragraph_boundary_check` после окончательной сборки + ERROR-событие + тест WP-G |
| Сессионные языки протекут в аудиокнигу | `language_pair_for_operation` во всех точках + `AppTest` переходов translate → audiobook |
| Пакеты разойдутся на общих файлах | волны + явный порядок + полный прогон после каждого переноса |
| Эмодзи-данные устареют при обновлении Python | гард версии R1 |

## Сохраняемые контракты AGENTS.md

- **WSL runtime:** все тесты и диагностические импорты — `wsl.exe -d Debian --cd "D:\Work\Projects\DocxAICorrector" --
  bash scripts/test.sh <selector> -q`, один selector на команду; Windows `python` и `.venv-win` не используются; в боковых
  worktree — только `wsl.exe -d Debian -- bash -lc '...'` с литеральными путями (без `$VAR` и циклов на границе).
- **Каноническая проверка:** финальное «зелёное» — полный `scripts/test.sh tests/ -q` в главном дереве при пустом
  `git status --porcelain`; debug-путь помечается `debug-only`.
- **Real-document evidence:** FR-009 — только `scripts/run-real-document-validation.sh`; при падении профиля — сначала
  отчёт прогона и `failed_checks` с `actual`/`threshold`; полный прогон — веха, не цикл настройки.
- **Логирование и артефакты:** события — `contracts/events.md`, регистрирует WP-H; полные тексты — не в лог; новых семей
  `.run/` нет; `.run/` и `.env` вне git.
- **Line endings:** все новые файлы — LF; после правок `git diff --check`.

## Что не определено (сказано прямо)

- **Доля ложных `fragment`** на переведённых DOCX — только snapshot FR-009 и чтение каждого срабатывания.
- **Порог покрытия 0,6** — без калибровки по ложным срабатываниям (на старых прогонах под ним 0 абзацев, Codex 10).
- **Справится ли flash-lite с числами словами в падеже** (Assumptions спеки) — SC-002 на FR-009.
- **Частота остатка до исправления и цена исправления** — неизвестны; бюджет ≈ 1 $ — оценка спеки, факт — SC-005.
- **Распознаёт ли подготовка роли TOC, таблиц, подписей и регион аппарата на переведённом DOCX** (Assumptions) —
  snapshot FR-009; нераспознанное звучит (FR-003, ограничение записано).
- **Символы `Emoji=Yes, Emoji_Presentation=No` без `U+FE0F` (☺, ✈)** остаются тексту (R1); как их прочтёт TTS — шаг
  прослушивания владельца.

## Complexity Tracking

Нарушений Конституции, требующих обоснования, нет.
