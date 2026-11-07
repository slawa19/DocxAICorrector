# Tasks: P2 спеки 063 — глоссарий прогона (FR-013…FR-016)

**Input**: `specs/063-translation-fidelity/` — `plan.md`, `research.md`, `data-model.md`,
`contracts/glossary.md`, `quickstart.md`. Только блок P2 (User Story 4 спеки).

**Tests**: обязательны — тест пишется первым в каждой задаче-паре и сначала падает. Проверка —
только `scripts/test.sh` через `wsl.exe`, по одному селектору на команду.

**Формат**: `[ID] [P?] [US4] Описание с путём`. `[P]` — можно параллельно (разные файлы).

## Phase 1: Foundational — запись и рендер (блокирует всё остальное)

- [X] T001 [US4] Тесты записи и рендера в `tests/test_glossary_pass.py`: у `GlossaryTerm` новые
  поля `kind="term"`, `note=""` по умолчанию; `render_glossary_prompt_section` — формат строки
  `- src -> tgt`, ` (имя)` для `kind="name"`, ` — note`; обрезка по бюджету символов с «- …»;
  нулевой бюджет → пустая строка; `DocumentContextProfile.to_prompt_text` режет по символам, а не
  по 8 записям (10 коротких записей помещаются целиком); анти-регресс богословского пути: профиль
  из `processing/preparation.py` для текста с «Great Tribulation» даёт те же записи, что до правки.
- [X] T002 [US4] `src/docxaicorrector/document/segments.py`: поля `kind`, `note` у `GlossaryTerm`;
  функция `render_glossary_prompt_section(terms, *, header, max_chars)`; `to_prompt_text` получает
  `max_glossary_chars` (константа `DEFAULT_GLOSSARY_PROMPT_MAX_CHARS = 3000`) вместо
  `max_glossary_terms` и рендерит через ту же функцию.
- [X] T003 [US4] `src/docxaicorrector/text/glossary_pass.py` (новый): `domain_glossary_terms(*,
  source_text, translation_domain)` — разбор строк `A -> B` плана `build_terminology_plan`;
  `src/docxaicorrector/processing/preparation.py:519-541` зовёт его (вывод тот же);
  `text/translation_domains.py` не меняется (FR-016).

## Phase 2: Извлечение кандидатов по форме (FR-013)

- [X] T004 [US4] Тесты извлечения в `tests/test_glossary_pass.py` на синтетических абзацах (без
  книжных литералов в продуктовом коде; в тестах — выдуманные слова): имя не в начале фразы
  ловится, «This»/«There» в начале нумерованной заметки — нет (тест регистра); аббревиатура
  ловится даже при строчном омониме; серия в начале фразы целиком — только при сигнале первого
  слова; курсив первого употребления ловится, курсив ударения на поздней встрече — нет;
  кавычки; конструкция определения (`refer to … as *X*`, `known as X)`), в том числе после
  статьи; коллокация с высоким G² ловится; «голова семейства»; URL не даёт кандидатов; Юникод
  в имени («Andrés»); одно вхождение — не кандидат; квоты семейств и общий лимит; порядок
  детерминирован; анти-вакуум: абзацы обычной прозы без терминов не дают служебных слов в
  `name` и `marked`.
- [X] T005 [US4] Реализация в `src/docxaicorrector/text/glossary_pass.py`:
  `GlossarySourceUnit`, `GlossaryCandidate`, `extract_glossary_candidates(units, *, limit)`,
  `select_glossary_source_units(jobs, source_paragraphs)` (регионы `prose` и `front_matter`,
  только `llm`-задания).

## Phase 3: Вызов модели (FR-013, FR-015, FR-016)

- [X] T006 [P] [US4] Тесты запроса и разбора в `tests/test_glossary_pass.py`: запрос содержит
  языки, `max_terms`, кандидатов с контекстом и доменные `fixed_terms`; кандидаты, совпавшие с
  доменными, из запроса убраны; разбор принимает только кандидатов (`not_a_candidate`), отбрасывает
  пустую передачу, нормирует `kind`, допускает вторую запись термина только с другим `note`,
  режет по `max_terms`; невалидный JSON → исключение с кодом.
- [X] T007 [US4] Реализация `build_glossary_request(...)`, `parse_glossary_response(...)` в
  `text/glossary_pass.py`; инструкция `src/docxaicorrector/resources/prompts/glossary_extraction.txt`.
- [X] T008 [P] [US4] Тест и реализация провайдерного вызова: `STAGE_GLOSSARY_EXTRACTION` в
  `src/docxaicorrector/core/model_accounting.py`; параметр `usage_stage` у трёх хелперов
  `src/docxaicorrector/generation/_generation.py` (по умолчанию прежняя стадия) и новая
  `request_text_completion(...)`; тест: стадия `glossary_extraction` попадает в учёт,
  `api_path_counts` не растёт, блоки по-прежнему пишут `text_generation`.

## Phase 4: Конфиг

- [X] T009 [P] [US4] Тесты в `tests/test_config.py`: ключи `glossary_pass_enabled` (true),
  `glossary_max_terms` (60), `glossary_prompt_max_chars` (3000), `glossary_candidate_limit` (400)
  из `config.toml`; env-переопределения `DOCX_AI_GLOSSARY_*`; зажимы диапазонов; `.env.example`
  документирует ключи.
- [X] T010 [US4] Реализация: `src/docxaicorrector/resources/config.toml`,
  `core/config_runtime_sections.py`, `core/config_loader_layers.py`, `core/config.py` (тип
  `AppConfig`), `.env.example`.

## Phase 5: Фаза пайплайна и видимость (FR-014, contract)

- [X] T011 [US4] Тесты фазы в `tests/test_glossary_pass.py` (двойники клиента, без сети):
  `translate` + ключ включён → вызов один, раздел дописан к `document_context_prompt` и виден в
  системном промпте блока; `edit`/`audiobook` и выключенный ключ → ни вызова, ни события, промпт
  тот же; нет кандидатов → без вызова, `no_candidates`; исключение клиента и мусор вместо JSON →
  прогон завершается, WARNING `run_glossary_failed`, промпт тот же; «Стоп» до вызова → `stopped`;
  артефакт записан в `.run/run_glossaries/` (каталог подменяется на tmp) и прунится; контекст
  события по контракту; уведомление `glossary` в `latest_result_notices` (`info` при `built`,
  `warning` при `failed`); фаза не трогает `delivery_disposition`.
- [X] T012 [US4] Реализация: `src/docxaicorrector/pipeline/glossary_phase.py` (новый);
  `pipeline/setup.py` (`execute_processing_run` зовёт `run_glossary_phase_fn`, если передана);
  `pipeline/_pipeline.py` (передаёт реализацию); `pipeline/contracts.py` (`ProcessingState`:
  статус и число терминов); `pipeline/late_phases.py` (уведомление);
  `runtime/artifact_retention.py` (`RUN_GLOSSARIES_*`); `core/constants.py` (`RUN_GLOSSARIES_DIR`).
- [X] T013 [P] [US4] UI: вид `glossary` в `_RENDERED_RESULT_NOTICE_KINDS`
  (`src/docxaicorrector/ui/_ui.py:753`), ключи `result.run_glossary_built` /
  `result.run_glossary_failed` в `ui/locales/ru.json` и `en.json`; существующие i18n-гарды
  зелёные.
- [X] T014 [P] [US4] Раннер: `tests/artifacts/real_document_pipeline/run_lietaer_validation.py` —
  секция `run_glossary` в отчёте (событие + артефакт), строки `run_glossary_*` в summary,
  `run_glossary=not_reported` без события; тесты в `tests/test_real_document_pipeline_validation.py`.
- [X] T015 [P] [US4] `docs/LOGGING_AND_ARTIFACT_RETENTION.md`: события `run_glossary_built`,
  `run_glossary_failed`, `run_glossary_artifact_write_failed` (§3.3), строка `.run/run_glossaries/`
  (§5.1), запись Changelog; тест retention по образцу `tests/test_runtime_artifact_retention.py`.

## Phase 6: Evidence

- [X] T016 [P] [US4] `scripts/measure-glossary-candidates.py` (WSL; подготовка без модели или
  готовый дамп; полнота против `terminology.json` рецензента; `--live` — один вызов извлечения
  через продуктовый путь с печатью токенов и стоимости); строка в `scripts/README.md`, группа 2;
  `tests/test_script_contract_static.py` зелёный.
- [X] T017 [P] [US4] `scripts/measure-glossary-consistency.py` (`python3 -I`, без импорта
  репозитория): по каждому термину глоссария — пары с термином в источнике, доля пар с
  закреплённой передачей (сравнение по основам), `idx` остальных; строка в `scripts/README.md`.
- [X] T018 [US4] Прогон T016 на четырёх книгах (без модели); числа полноты и пропуски — в
  Changelog спеки (сверка с research R3 на продуктовом коде, а не на прототипе).
- [X] T019 [US4] Один живой вызов извлечения на одной книге (≤ $0,50): число записей, токены,
  стоимость, символы раздела промпта, отношение символов к токенам; какие термины M-1/M-4 попали
  в глоссарий. Полную книгу не прогонять.
- [X] T020 [US4] T017 по `pairs.jsonl` прогона 2026-11-07 той же книги с глоссарием T019 —
  исходная точка SC-006 («без глоссария»).

## Final Phase

- [X] T021 Changelog-строка P2 в `specs/063-translation-fidelity/spec.md` (строку Status не
  трогать — её ведёт оркестратор).
- [X] T022 `git diff --check`; модули тестов P2; `tests/test_config.py`;
  `tests/test_document_pipeline.py`; `tests/test_script_contract_static.py`;
  `tests/test_spec_status_consistency.py`; pyright `tests/test_typecheck.py`; полный прогон
  `scripts/test.sh tests/ -q` в `wt-063g`.

## Dependencies & strategy

T001→T002→T003 блокируют всё. T004→T005, T006→T007 последовательно; T008 и T009/T010 — параллельно
с ними. T011→T012 требует T002…T010. T013–T015 после T012. T016/T017 после T005/T007/T008;
T018→T019→T020 строго по порядку (T019 тратит деньги — только после зелёных T001–T017). Каждая
задача-пара: тест → падение → код → зелёный → коммит кластера.
