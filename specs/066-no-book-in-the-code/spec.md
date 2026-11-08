# Feature Specification: В коде нет книги — удаление литералов тестовых книг, домена `theology` и мёртвых осей удалённых фич

**Feature Branch**: `[066-no-book-in-the-code]`

**Created**: 2026-11-08

**Date**: 2026-11-08 (строки кода проверены на `88a5fa8`, последнем коммите `main` на эту дату)

**Status**: **IN PROGRESS (2026-11-08) — четыре пакета работ реализованы агентами и влиты в
`066/integration` (P4 `8efa348`, P2 `0ae4286`, P1 `b157942`, P3 `fc7fd36`; C-4 отозвана), хвосты
после слияния (P5), полный прогон в главном дереве и приёмочное ревью Codex — до слияния в `main`.**
Спека написана по сплошному обходу `src/docxaicorrector/` (агент, 95 обращений к файлам) и
выборочной перепроверке оркестратором. Spec-only tier
(Конституция III): каждая правка — удаление или переименование по форме, ограниченное названной
находкой; проверка — детерминированная: полный прогон, офлайн-replay сборки четырёх книг третьего
прогона и structural-preparation snapshot без модели. `plan.md` и `tasks.md` не пишутся. Решений
владельца не требуется: единственное продуктовое решение уже принято (см. «Решения владельца»).

**Owner surface**: `text/translation_domains.py` и `resources/prompts/domains/` (удаляются);
`core/config.py` (`load_system_prompt`: kwargs `translation_domain`, `source_text`),
`core/config_runtime_sections.py`, `core/config_loader_layers.py`, `core/config_structure_sections.py`,
`core/config_model_registry.py`, `core/models.py`; `pipeline/support.py`, `pipeline/glossary_phase.py`,
`pipeline/output_validation.py`, `pipeline/quality_gate.py`, `pipeline/display_hygiene.py`,
`pipeline/contracts.py`, `pipeline/_pipeline.py`, `pipeline/setup.py`; `processing/preparation.py`,
`processing/application_flow.py`, `processing/processing_service.py`; `document/segments.py`,
`document/extraction.py`, `document/roles.py`, `document/structure_repair.py`, `document/layout_cleanup.py`,
`document/relations.py`, `document/semantic_blocks.py`, `document/boundary_review.py`;
`structure/validation.py`, `structure/layout_signals.py`; `validation/acceptance.py`, `validation/structural.py`,
`validation/structural_checks.py`, `validation/structural_unit_alignment.py`, `validation/structural_toc_signals.py`,
`validation/structural_prep_snapshot_helpers.py`, `validation/quality_gate_audit.py`, `validation/profiles.py`;
`runtime/artifact_retention.py`; `generation/_generation.py`, `generation/search.py`, `image/model_capabilities.py`,
`image/generation.py`, `image/shared.py`, `image/pipeline.py`; `ui/_app.py`, `ui/locales/*.json`;
`resources/prompts/system_prompt.txt`, `example_toc_translate.txt`, `example_audiobook.txt`,
`structure_recognition_system.txt`, `document_map_system.txt`, `reconciliation_targeted_system.txt`;
`resources/config.toml`; `tests/artifacts/real_document_pipeline/run_lietaer_validation.py` и фикстуры
`tests/fixtures/late_phases_characterization/`, `tests/fixtures/structural_validation_characterization/`,
`tests/fixtures/output_validation_characterization/`.

**Companion**: `specs/065-glossary-reaches-the-reader/spec.md` (глоссарий прогона — автоматическая
замена удаляемого доменного списка; её D1 закрыт решением ниже); `specs/063-translation-fidelity/spec.md`
(FR-016 говорил «богословский список не трогать» — эта спека его отменяет, см. Changelog 063);
`specs/064-context-never-reached-the-model/spec.md` (R-1: `source_text` в `load_system_prompt` был
входом сканера доменных терминов — здесь этот вход удаляется вместе со сканером);
`.specify/memory/constitution.md` Принцип VII (правила по форме, без литералов под книгу).

## Что найдено

Повод — вопрос владельца 2026-11-08: «доменный глоссарий» в коде оказался зашитым списком десяти
эсхатологических терминов из тестовой книги апреля 2026 (`c53f9a5`). Сплошной обход показал, что это
не единичный случай: в `src/` живут литералы трёх тестовых книг, промпт-пример с оглавлением
*The Value of Everything*, и остатки двух удалённых фич — AI-first распознавания структуры и
topology-проекции, — которые тянутся примерно через пятнадцать модулей, печатаются в каждом
`preparation_diagnostic_snapshot` (`"ai_first_degraded": false`, `"document_map_status":
"not_requested"`, `"structure_ai_attempted": false` — так в `run_summary.txt` всех четырёх книг
третьего прогона) и валидируются при каждой загрузке конфига.

| Группа | Находок | Удалить | Обобщить по форме | Наблюдать | Оставить |
|---|---|---|---|---|---|
| A — литералы книг и домена | 2 подтверждённых + 6 | 5 | 3 | — | — |
| B — старые модели и API | 5 | 1 | 1 | 1 | 2 |
| C — мёртвые оси удалённых фич | 13 | 11 | 1 | — | 1 |
| D — структурные словари | 9 | — | — | — | 9 |

Критерий «мёртвости» один и проверяемый: ключ не производится ни загрузчиком конфига
(`core/config*.py`), ни `resources/config.toml`, ни UI, ни профилями валидации — только тесты
подкладывают его напрямую. Такой ключ в продукте недостижим, и его ветки — мёртвый код с живыми
тестами.
Читателей надо искать и в каноническом раннере
`tests/artifacts/real_document_pipeline/run_lietaer_validation.py`, не только в `src/`: на этом
споткнулась C-4.

## Verified findings

Пути — относительно `src/docxaicorrector/`. Пометка ✔ — строки перепроверены оркестратором по коду
или данным; остальные взяты из отчёта обхода, и исполнитель перепроверяет их перед правкой (Конституция
VIII). «Пин» — тесты, которые сейчас закрепляют поведение и будут переписаны или удалены.

### T — домен `theology` и его шлейф (подтверждено до обхода)

- **T-1 (P0) ✔. Домен перевода `theology` — единственный домен, и он недостижим.**
  `text/translation_domains.py:11-22` — десять regex англоязычных эсхатологических терминов;
  `:26-47` читает `resources/prompts/domains/theology_glossary_ru.txt` (10 строк вида
  `Great Tribulation -> Великая скорбь`); `:49-74` `build_terminology_plan` сканирует текст блока этими
  regex. Включается только `translation_domain_default = "theology"`
  (`core/config_runtime_sections.py:528,575-577`, env `DOCX_AI_TRANSLATION_DOMAIN_DEFAULT`); в
  `resources/config.toml` ключа нет, в UI нет, в профилях нет. Следствие для каждого прогона: секция
  `### ДОМЕН И ТЕРМИНОЛОГИЯ:` системного промпта (`resources/prompts/system_prompt.txt:17-18`) всегда
  печатает «Специальные доменные инструкции не заданы.» (`core/config.py:1726-1731`), строка
  `- Домен: general` печатается в контексте документа (`document/segments.py:228-229`), а
  `pipeline/glossary_phase.py:340-342` каждый раз вызывает `domain_glossary_terms` ради пустого
  кортежа. Сантехника: `pipeline/support.py:28-38` (`resolve_prompt_source_text` — ровно тот вход,
  который в спеке 064 R-1 перехватывал контекст документа), `processing/preparation.py:54-55,101,
  328-368,520-574`, `pipeline/contracts.py:60,244`, `pipeline/_pipeline.py:147-158`,
  `pipeline/setup.py:229`, `processing/application_flow.py:128,420`, `pipeline/quality_gate.py:1521,2032`,
  `validation/profiles.py:66,455` (`require_translation_domain`), `validation/structural.py:520`
  (`runtime_translation_domain`), `validation/structural_checks.py:587-593`. Пин: `tests/test_translation_domains.py`,
  `test_config.py:268-272,623-635,675`, `test_document_pipeline.py:3343-3731`, `test_glossary_pass.py`,
  `test_processing_service.py`, `test_preparation.py`, `test_real_document_validation_corpus.py:663-687,
  933-941,1030-1038`, `test_real_document_pipeline_validation.py`, `test_pdf_candidate_benchmark_project.py`.
  **Удалить ось целиком.** Автоматическая замена уже есть — глоссарий прогона (спека 063 P2, 064 R-1,
  065).
- **T-2 (P0) ✔. Счётчики `theology_style_deterministic_issue_*` зашиты нулями и печатаются в каждом
  отчёте.** `pipeline/quality_gate.py:2150-2153` и `validation/structural_checks.py:92-95` — четыре
  поля с константами `0` / `"legacy_markdown"` / `"domain_style_advisory"`; проверка приёмки
  `theology_style_deterministic_issues_present` (`validation/acceptance.py:57,905-913`,
  `validation/structural.py:206-209`), локали `result.acceptance_check.theology_style_deterministic_issues_present`
  (`ui/locales/ru.json:159`, `en.json:158`), печать в `run_lietaer_validation.py:695-698,1290-1297`.
  Пин: семь фикстур `tests/fixtures/late_phases_characterization/*.json`, `test_document_pipeline.py:5373-5381`,
  `test_real_document_validation_corpus.py:1147-1149,1186-1187`. **Удалить поля и проверку.**

### A — литералы книг в продукте

- **A-1 (P0) ✔.** `pipeline/output_validation.py:90`
  `_CANONICAL_JUDGMENT_HEADING_PATTERN = r"^суд\b.+\(откровение\s+\d{1,3}:\d{1,3}"` — заголовок «Суд …
  (Откровение N:N)» одной книги; `:849` освобождает такие заголовки от детектора ложных фрагментов.
  Работает в каждом прогоне. Пин: `test_document_pipeline_output_validation.py:2460`. **Удалить.**
- **A-2 (P0) ✔.** `validation/quality_gate_audit.py:15,31,37,48,54,70` — ключ
  `heldout_money_sustainability_class` с классами вида `b_extraction_noise_front_matter_title_split`
  внутри таблицы аудита шлюза; попадает в каждый отчёт через `pipeline/quality_gate.py:2159` и
  `validation/structural_checks.py:113`. Пин: шесть фикстур late_phases, `test_structure_validation.py`.
  **Удалить ключ**; нейтральные поля классификации той же таблицы остаются.
- **A-3 (P0) ✔.** `resources/prompts/example_toc_translate.txt:10-17` — пример оглавления
  `Introduction: Making Versus Taking … 1`, `Part II: The Dynamics of Extraction … 83`: настоящие
  заголовки *The Value of Everything*, книги валидационного корпуса. Вариант `toc_translate`
  выбирается для блоков оглавления в режиме перевода (`core/config.py:1689-1693`,
  `pipeline/block_execution.py:875`). Пин: `test_config.py:1113` и sha256-снимки промптов.
  **Заменить вымышленным оглавлением** той же формы (часть / глава / введение, точки-лидеры, номера).
- **A-4 (P1) ✔.** `pipeline/output_validation.py:119-121`
  `_RUSSIAN_PRONOUN_CONTINUATION_START_PATTERN` — список местоимений × список глагольных основ
  (`смог|буд|хот|мож|долж|стан|готов|суме`); `:1737` разрешает по нему слияние двух записей при
  сборке. Фикстура теста — «Я смогу выдержать до конца.» из той же эсхатологической книги. Пин:
  `test_document_pipeline_output_validation.py:2311-2347`. **Удалить**: правило строчного начала
  (`:118`) — форменное и остаётся; replay сборки (SC-002) покажет, срабатывал ли список на корпусе.
- **A-5 (P1).** Кластер `scripture_reference`: правило по форме «Слово N:N», носящее богословское имя.
  `pipeline/output_validation.py:85-87` (`_SCRIPTURE_REFERENCE_HEADING_PATTERN`, причина
  `scripture_reference_heading_present` `:2083,2257,2392`, освобождение
  `_entry_is_source_backed_scripture_heading` `:904-949`), `pipeline/display_hygiene.py:18,348`,
  `document/structure_repair.py:22,551`, `pipeline/quality_gate.py:1569,2103-2104`
  (`scripture_reference_heading_count`), `validation/quality_gate_audit.py:18`,
  `validation/structural_checks.py:60,97`, `validation/structural.py:197`, поле
  `scripture_reference_hint` (`core/models.py:360-371`, C-5). Срабатывает и на «(Time 10:30)». Пин:
  фикстуры late_phases и `output_validation_characterization/collect_samples.json`,
  `test_document_pipeline.py`, `test_document_pipeline_output_validation.py:326,2392`,
  `test_real_document_validation_corpus.py`. **Переименовать по форме** в `numbered_citation`
  (заголовок-ссылка «Слово N:N»): правило остаётся, имя и ключи отчёта меняются, контракт отчёта
  (`docs/LOGGING_AND_ARTIFACT_RETENTION.md`) — вслед.
- **A-6 (P1) ✔.** `resources/prompts/example_audiobook.txt:20,23` — абзац про обратный выкуп акций и
  вознаграждение топ-менеджеров: тезис введения *The Value of Everything*. Пин: нет. **Заменить
  вымышленным абзацем** той же длины и формы (два предложения с вводной и причинной связью).

### B — старые модели и устаревший API

- **B-1 (P1, наблюдать) ✔.** `generation/_generation.py:1917` — `"temperature": 0.4` в каждом
  текстовом запросе (также `text/glossary_pass.py:960` — 0.2, `image/reconstruction.py:163` — 0.0).
  Параметр снимается только после отказа провайдера (`image/shared.py:197-213`,
  `_generation.py:1606`), снятие не запоминается между вызовами и **не логируется**. Проверено на
  третьем прогоне: в `run_full.log` четырёх книг упоминаний `unsupported`/`temperature` нет, число
  вызовов равно числу блоков плюс глоссарий и ретраи (Money 293 вызова на 270 блоков) — лишнего вызова
  на блок нет. Но отсутствие лога ничего не доказывает, потому что снятие молчаливое. **Не удалять;
  добавить WARNING-событие при снятии параметра** (`model_call_param_dropped`: `{param, model,
  stage}`), решать по четвёртому прогону.
- **B-2 (P1) ✔.** `image/model_capabilities.py:67,91,111,293-294` — `accepts_response_format` False
  у всех строк, ветка `payload["response_format"] = "b64_json"` недостижима; `"response_format"` ещё
  числится retryable в `image/generation.py:670,780`. Наследие dall-e. Пин: нет. **Удалить.**
- **B-3 (P2) ✔.** `generation/_generation.py:1657-1667` — `_normalize_anthropic_model_id` с таблицей
  из одной модели (`claude-sonnet-4.6 → claude-sonnet-4-6`). Срабатывает только на id, набранный
  вручную с точкой. **Обобщить по форме**: точка между цифрами в хвосте id → дефис, без таблицы.
- **B-4 (оставить).** `image/model_capabilities.py:104-120` — строка `gpt-image-1.5` с пометкой
  «Retires 2026-12-01». Законна до даты; удаление — отдельной правкой после неё (Non-goals).
- **B-5 (оставить).** `generation/_generation.py:1624-1640,1959` — fallback OpenRouter Responses →
  Chat Completions: совместимость провайдера, не модели.

### C — мёртвые оси и остатки удалённых фич

- **C-1 (P0) ✔. Ось `structure_recovery` (`ai_first` / `signal_only`).** Ключи
  `structure_recovery_enabled` / `structure_recovery_mode` не производит ни один загрузчик
  (`grep` по `core/` и `config.toml` — пусто), поэтому `_resolve_structure_recovery_runtime`
  (`document/extraction.py:1030-1039`) всегда возвращает `(False, "legacy")`. Мёртвые ветки:
  `document/extraction.py:225-310,639-656`, `document/roles.py:205-326`,
  `document/structure_repair.py:34-38` и ~15 веток `signal_only`, `document/layout_cleanup.py:85`,
  `processing/preparation.py:329-370,1052-1110`; фаза `ai_first_degraded_fallback` сравнивается, но
  не присваивается (`document/relations.py:384`, `document/segments.py:982`,
  `document/semantic_blocks.py:492,533`); `role_confidence == "ai"` не присваивается
  (`document/roles.py:216`, `document/segments.py:609,996`, `structure/validation.py:90`). Пин:
  `test_document_extraction.py`, `test_document_layout_cleanup.py`, `test_document_structure_blocks.py`,
  `test_document_structure_repair.py`, `test_paragraph_boundary_normalization.py`, `test_preparation.py`.
  **Удалить.**
- **C-2 (P0) ✔. Путь topology-проекции / document map.** Продукт всегда передаёт
  `document_map=None, topology_projection=None` (`pipeline/quality_gate.py:2208-2263`, комментарий
  «Structure recognition (#2) removed»); события `structure_processing_outcome`,
  `document_topology_projection_built/skipped`, `document_topology_layout_signals_built` в `src/` не
  эмитирует никто (`grep` вне `validation/` — пусто). Мёртвое: `validation/structural_unit_alignment.py:553-683`
  (ветка `topology_unit`), `validation/structural_toc_signals.py:40-298` (большая часть),
  `validation/structural.py:567,757-870`, `validation/structural_prep_snapshot_helpers.py:144-165`
  (ключи `structure_recovery_topology_projection_*`, из-за чего `structure/layout_signals.py`
  недостижим), `validation/acceptance.py:211,319,395-430`, `validation/structural_checks.py:121-153,
  372-384,515-581`, `runtime/artifact_retention.py:59-60` (`DOCUMENT_TOPOLOGY_MAX_*`). Пин: фикстуры
  `structural_validation_characterization/cluster_d_gate_fields_topology.json`,
  `cluster_e_unmapped_fields_topology.json`, `orchestrator_prep_snapshot.json`;
  `test_structural_validation_characterization.py`, `test_gate_detectors_stage2.py`,
  `test_structure_layout_signals.py`, `test_structural_checks_coverage_review_data.py`,
  `test_preparation.py`, `test_real_document_pipeline_validation.py`. **Удалить.**
- **C-3 (P0) ✔. Три файла промптов-сирот.** `resources/prompts/structure_recognition_system.txt`,
  `document_map_system.txt`, `reconciliation_targeted_system.txt` — не загружает никто в `src/`,
  `tests/`, `scripts/`; первый несёт пример `Mark 13:13 / Марк 13:13` (:53-54). **Удалить.**
- **C-4 — ОТОЗВАНА 2026-11-08 (исполнитель P3, проверено оркестратором).** Reader-verifier не удалён, а
  выключен по умолчанию (`bb24e49`): его читает канонический раннер валидации
  `tests/artifacts/real_document_pipeline/run_lietaer_validation.py:2176-2198`
  (`_resolve_reader_verifier_config` читает `reader_verifier_enabled` и `reader_verifier_model`,
  вызовы `:3102`, `:6086`), а десять run-профилей `corpus_registry.toml` ставят
  `reader_verifier_enabled = false`. По критерию этой спеки (производят профили, читает раннер) это
  opt-in фича оценки, не мёртвый ключ. Обход агента искал читателей только в `src/` и раннер не
  увидел. Удаление подсистемы (~258 ссылок в раннере) — решение владельца, здесь не делается.
  Первоначальная формулировка: `resources/config.toml:81` `reader_verifier_model`, парсинг
  `core/config_runtime_sections.py:127-133`, `validation/profiles.py:102,309,339-340,524`.
- **C-5 (P0) ✔. Поля Stage-0 и класс-дескриптор для удалённого AI.**
  `document/extraction.py:312,756-880` (`_annotate_stage0_structure_signals`) пишет `style_cluster_id`,
  `font_size_z_score`, `position_fraction`, `is_isolated_marker`, `toc_pattern_hint`,
  `scripture_reference_hint` (`core/models.py:360-371`) — читателей нет; `core/models.py:394-455`
  `ParagraphDescriptor` и `to_prompt_dict` (поле `"scr"`) — ноль ссылок. Пин: `test_document_extraction.py`.
  **Удалить.**
- **C-6 (P0) ✔. Нечитаемые ключи и мёртвый отладочный writer.** `structure_validation_enabled`,
  `structure_validation_save_debug_artifacts`, `structure_validation_block_on_high_risk_noop` парсятся
  (`core/config_structure_sections.py:205-317`, `core/config_loader_layers.py:111,130-134`) и не
  читаются; `structure/validation.py:427-447` `write_structure_validation_debug_artifact` без
  вызывающих, читает несуществующие `structure_recognition_mode` / `_model`. Пин: `test_config.py`,
  `test_preparation.py`, `test_structure_validation.py:271-307`. **Удалить.**
- **C-7 (P0) ✔. Regex, который не может совпасть.** `pipeline/output_validation.py:117`
  `_RUSSIAN_CONTINUATION_ENDING_PATTERN` (`…|является)$`): оба вызывающих (`:727`, `:1726`)
  возвращают раньше, если `_SENTENCE_TERMINAL_PATTERN` (`:133`, требует `.!?…:` в конце) не совпал, а
  тогда строка кончается знаком, не словом. Словарный список, работавший бы вопреки Принципу VII,
  если бы работал. **Удалить** вместе с двумя `return`-хвостами.
- **C-8 (P0) ✔.** `processing/processing_service.py:426`, `ui/_app.py:339`,
  `structure/validation.py:437` читают `app_config["structure_recognition_model"]`, который не
  производится. Пин: `test_processing_service.py:413,546,623,635`, `test_preparation.py:227-267`.
  **Удалить.**
- **C-9 (P1) ✔. Роль `models.structure_recognition`.** `core/config.py:100,158,1455-1470`,
  `core/config_model_registry.py:250,371,429-540`; читает legacy-ключ `structure_recognition.model` и
  env `DOCX_AI_STRUCTURE_RECOGNITION_MODEL`; единственный потребитель — `document/boundary_review.py:35`
  (`paragraph_boundary_ai_review`, по умолчанию выключен, в UI не выведен); валидируется при каждой
  загрузке конфига. В `config.toml:120` секция закомментирована. **Переименовать роль в
  `boundary_review`** и удалить legacy-источники (ключ `structure_recognition.model`, env). Старое имя
  не принимается молча: это была бы новая совместимостная прослойка на месте удаляемой.
- **C-10 (P1).** `validation/structural_prep_snapshot_helpers.py:40-56,420-426` —
  `_HUMANIZED_QUALITY_GATE_REASON_TO_CODE`: 13 из 15 русских строк-причин в `src/` не производятся
  (среди них «AI-распознавание структуры не внесло изменений…», ведущая в ветку
  `structure_recognition_noop_on_high_risk`). Пин: `orchestrator_prep_snapshot.json`. **Удалить
  непроизводимые записи** (исполнитель перечисляет, какие две живы, по `grep` производителей).
- **C-11 (P1) ✔.** `generation/search.py` — dev-скрипт, грепающий каталог по `("gpt-", "gpt-4",
  "gpt-5", "gpt-image")`; в пакете, приложение не импортирует. Пин: `test_root_shim_identity_aliases.py:35`,
  `test_script_contract_static.py:492` (CODEOWNERS). **Удалить** вместе со строкой CODEOWNERS.
- **C-12 (P1) ✔.** `image/pipeline.py:1422` — `image_model_call_budget_per_document` и
  `semantic_redraw_max_model_calls_per_document`: ни один ключ не производится конфигом. Пин:
  `test_image_integration.py`, `test_image_pipeline_compare_helpers.py` (подкладывают ключ).
  **Удалить** мёртвый override, оставив живой путь бюджета.
- **C-13 (оставить).** `pipeline/reassembly.py:13` `OutputMode = Literal["legacy_full_document"]` —
  ось с одним значением (`pipeline/setup.py:217`, `ui/_app.py:1158`). Схлопывание — косметика с
  тремя пинами; Non-goals.

### D — структурные словари (оставить, записано для полноты)

Все девять — слова роли или региона документа, не книги: `reader_cleanup_mvp/_constants.py:202-249`
(соединители и типовые токены колонтитулов), `document/structure_repair.py:23-26`,
`document/boundaries.py:16-37` (служебные слова title-case оглавления),
`validation/formatting_coverage.py:30-82`, `document/semantic_blocks.py:48-82`,
`pdf_import/logical_import.py:1550-1557`, словари секций и мебели страницы
(`document/extraction.py:173-176`, `document/roles.py:101,394`, `pipeline/display_hygiene.py:21-24`,
`document/layout_cleanup.py:35-38`, `structure/page_furniture_detection.py:16-20`,
`pipeline/quality_gate_text_detectors.py:37-39`), `text/glossary_pass.py:119-126`
(конструкции определения), `pipeline/narration_postprocess.py:43` (теги TTS). Две странности
`_HEADER_CONNECTOR_WORDS` (местоимение `мы`, польское `dla`, дубль `appendix`) — в Non-goals как
заметка, не правка.

## Решения владельца

- **Ручного входа в глоссарий нет** (владелец, 2026-11-08: «никакого редактора в UI — всё должно
  быть максимально автоматически»). Закрывает D1 спеки 065: ни редактора в UI, ни файла-сайдкара рядом
  с книгой. Передачи выбирает модель по глоссарию прогона; единственный ручной рычаг остаётся прежним
  — правка готового артефакта перевода. Записано в Non-goals 065.
- **Домен `theology` удаляется вместе с осью `translation_domain`**, а не заменяется «общим доменом»:
  автоматическая замена — глоссарий прогона — уже доставляется модели (064 R-1). Отменяет FR-016
  спеки 063 («список не трогать»): тот пункт защищал список от расширения, а не от удаления, и
  удаление — обратное расширению.

## Requirements *(mandatory)*

- **FR-001 (T-1)**: модуль `text/translation_domains.py`, каталог `resources/prompts/domains/`, ключ
  `translation_domain_default` с env-переменной, kwargs `translation_domain` и `source_text` у
  `load_system_prompt`, поле `translation_domain` у контекста документа / контрактов конвейера /
  профилей (`require_translation_domain`, `runtime_translation_domain`), `resolve_prompt_source_text`,
  `domain_glossary_terms` и `fixed_terms` в фазе глоссария удалены. Секция `### ДОМЕН И ТЕРМИНОЛОГИЯ:`
  из `system_prompt.txt` удалена (sha256-снимки четырёх вариантов в `test_config.py` обновлены с
  записью новых значений в Changelog); строка `- Домен:` из контекста документа удалена.
- **FR-002 (T-2)**: четыре поля `theology_style_deterministic_*`, проверка приёмки
  `theology_style_deterministic_issues_present`, две локальные строки и печать в
  `run_lietaer_validation.py` удалены; фикстуры late_phases перегенерированы или отредактированы так,
  чтобы полей не было; `docs/LOGGING_AND_ARTIFACT_RETENTION.md` не упоминает их.
- **FR-003 (A-1, A-4, C-7)**: три константы и их вызывающие ветки в `output_validation.py` удалены;
  замер SC-002 записан в Changelog (срабатывал ли каждый из трёх на корпусе — по replay).
- **FR-004 (A-2)**: ключ `heldout_money_sustainability_class` удалён из таблицы аудита и из отчётов;
  фикстуры обновлены.
- **FR-005 (A-3, A-6)**: оба примера заменены вымышленным содержанием той же формы; ни одно слово
  заголовков книг корпуса (`tests/artifacts/real_document_pipeline/` профили) не встречается в
  `resources/prompts/`. Гард: тест, который берёт заголовки книг из профилей корпуса и ищет их в
  `resources/prompts/*.txt` (правило формы: литерал книги узнаётся по совпадению с корпусом, не по
  словарю).
- **FR-006 (A-5)**: кластер `scripture_reference*` переименован в `numbered_citation*` во всех
  поверхностях (код, ключи отчётов, фикстуры, документация контракта); поведение правила не меняется
  (SC-002 — идентичный replay).
- **FR-007 (B-1)**: при снятии необязательного параметра запроса после отказа провайдера пишется
  WARNING `model_call_param_dropped` с `{param, model, stage, error_code}`; событие внесено в
  `docs/LOGGING_AND_ARTIFACT_RETENTION.md`. `temperature` остаётся.
- **FR-008 (B-2, B-3)**: `accepts_response_format` и ветка `response_format` удалены; таблица
  алиасов Anthropic заменена нормализацией по форме (цифровой хвост `x.y` → `x-y`) с тестом на
  `claude-sonnet-4.6`, `claude-opus-4.1` и уже каноничный id.
- **FR-009 (C-1, C-5, C-6, C-8, C-9)**: ось `structure_recovery` с ветками `signal_only`, фаза
  `ai_first_degraded_fallback`, `role_confidence == "ai"`, Stage-0 поля и `ParagraphDescriptor`,
  три ключа `structure_validation_*`, `write_structure_validation_debug_artifact`, чтение
  `structure_recognition_model` удалены; роль `structure_recognition` переименована в
  `boundary_review`, legacy-ключ и env удалены; поля `ai_first_degraded`, `structure_ai_attempted`,
  `ai_classified_count`, `ai_heading_count`, `structure_*` счётчики AI-распознавания исчезают из
  `preparation_diagnostic_snapshot`. Контракт snapshot в документации — вслед.
- **FR-010 (C-2, C-3, C-4, C-10)**: ветки `topology_unit` / `topology_*` / `document_map`, чтение
  неэмитируемых событий, `structure/layout_signals.py`, константы `DOCUMENT_TOPOLOGY_MAX_*`, три
  файла промптов, непроизводимые записи `_HUMANIZED_QUALITY_GATE_REASON_TO_CODE` удалены
  (`reader_verifier_*` остаётся — C-4 отозвана); фикстуры `*_topology.json` удалены, если
  проверяют только удалённые ветки, иначе урезаны.
- **FR-011 (C-11, C-12)**: `generation/search.py` удалён (CODEOWNERS, тест identity-aliases и
  статический контракт скриптов обновлены); мёртвый override бюджета в `image/pipeline.py:1422`
  удалён.
- **FR-012 (гард)**: тест формы «ключ конфига, который никто не читает»: для каждого ключа, который
  производят `core/config*.py`, есть чтение вне `core/config*.py` и тестов (`grep` по `src/`);
  исключения перечисляются в тесте с причиной. Тот же тест ловит обратное — чтение ключа, который
  никто не производит (`app_config.get("…")` с литералом, которого нет среди произведённых).
  Это единственный новый гард спеки, и он должен падать на `88a5fa8` минимум на C-1, C-4, C-6, C-8, C-12.

## Success Criteria *(mandatory)*

- **SC-001**: полный прогон `bash scripts/test.sh tests/ -q` зелёный в главном дереве после слияния
  всех пакетов; `git status --porcelain` пуст.
- **SC-002 (replay сборки)**: для четырёх книг третьего прогона (`D:\Temp\docxai-runs\2026-11-07-translate-third\<slug>\
  <report>.json`, `runtime.state.processed_block_markdowns` + `processed_paragraph_registry`)
  replay сборки производственным `output_validation` + `reader_cleanup_rebuild` до и после правок
  даёт побайтово равные итоговый markdown и итоговый реестр. Механика — как в
  `tests/test_spec_063_apparatus_policy.py::test_fr006_replay_on_recorded_translate_runs`. Если
  replay расходится, расхождение разбирается и записывается до слияния: удалённое правило срабатывало
  на корпусе.
- **SC-003 (snapshot подготовки без модели)**: `bash scripts/run-structural-preparation-diagnostic.sh
  <profile>` для четырёх профилей корпуса до и после даёт равные snapshot'ы с точностью до удалённых
  ключей (список удалённых ключей — в Changelog).
- **SC-004**: `grep -rn "theology\|Откровение\|tribulation\|Money and Sustainability\|Making Versus
  Taking\|heldout_money" src/` пуст; `grep -rn "structure_recovery\|topology_projection\|document_map\|
  reader_verifier\|ai_first" src/` пуст, кроме явно перечисленных в Changelog исключений (например,
  комментарий-эпитафия в `quality_gate.py`, если решено оставить).
- **SC-005**: гард FR-012 падает на `88a5fa8` и проходит после правок.
- **SC-006**: приёмочное ревью Codex по всем затронутым поверхностям (правило AGENTS.md) проведено до
  слияния в `main`, отчёт — `docs/reviews/CODEX_REVIEW_066_<дата>.md`.

## Non-goals

- Не трогать структурные словари группы D, включая странности `_HEADER_CONNECTOR_WORDS` (`мы`,
  `dla`, дубль `appendix`): это другая спека, если она вообще нужна; здесь — заметка.
- Не удалять `temperature` (B-1): доказательства отказа нет; сначала наблюдаемость (FR-007).
- Не удалять строку `gpt-image-1.5` (B-4) до 2026-12-01 и fallback OpenRouter (B-5).
- Не схлопывать `OutputMode` (C-13).
- Не делать ручной вход в глоссарий — ни в UI, ни файлом (решение владельца 2026-11-08).
- Не вводить «общий домен» или новый механизм доменных инструкций взамен удаляемого: доменную
  терминологию даёт глоссарий прогона.
- Не оставлять алиасы совместимости для удаляемых ключей конфига и env-переменных: старый ключ в
  пользовательском `config.toml` должен игнорироваться с WARNING `config_key_ignored` (один общий
  механизм для неизвестных ключей, если его нет — завести в рамках FR-012), а не поддерживаться.
- Не переписывать характеризационные фикстуры «начисто»: только удалять исчезнувшие поля, чтобы диф
  фикстур читался как список удалённого.

## Anti-regression

- Канонический прогон только через WSL-транспорт `wsl.exe -d Debian --cd "D:\Work\Projects\DocxAICorrector" --
  bash scripts/test.sh <selector> -q`; один селектор на команду; никаких Windows-python и прямых pytest.
- Боковые worktree агентов — вне репозитория (`D:\Temp\claude\wt-066-<pkg>`), `.venv` симлинком;
  git в worktree — только из Git Bash; `$VAR` через границу `wsl.exe` не передавать.
- Перед слиянием каждого пакета — его целевые тесты; после слияния всех — полный прогон в главном
  дереве; перенос на свежий `main` требует повторного полного прогона.
- Replay SC-002 и snapshot SC-003 снимаются ДО первой правки в пакете (эталон) и после последней;
  эталоны кладутся в `D:\Temp\docxai-research\066-baseline\` (вне git), пути — в Changelog.
- Тема коммита несёт номер 066 только у коммитов этой работы; артефакты — `artifacts:`.
- Удаление поля отчёта сопровождается правкой `docs/LOGGING_AND_ARTIFACT_RETENTION.md` и локалей в
  одном коммите с кодом — тест `tests/test_documentation_links.py` и гард контракта агента не должны
  краснеть между коммитами.
- `git diff --check` перед каждым коммитом (LF, trailing whitespace).

## Assumptions

- Третий прогон и его отчёты (`D:\Temp\docxai-runs\2026-11-07-translate-third\`) доступны и содержат
  `runtime.state` с `processed_block_markdowns` и `processed_paragraph_registry` (проверено для
  `value_of_everything` и `money_sustainability` 2026-11-08).
- LibreOffice в WSL на месте: SC-003 импортирует PDF корпуса.
- Строки из отчёта обхода без пометки ✔ могут сдвинуться; исполнитель перепроверяет перед правкой и
  исправляет номер в Changelog, а не в теле находки.

## Пакеты работ

Четыре непересекающихся по модулям пакета; общие файлы (`core/config*.py`, `test_config.py`,
`processing/preparation.py`, `validation/structural_checks.py`, `validation/acceptance.py`) правятся
в разных hunk'ах, конфликты сводит оркестратор при слиянии.

| Пакет | Ветка | Находки | Главные поверхности |
|---|---|---|---|
| P1 domain-and-literals | `066/domain` | T-1, T-2, A-1…A-6, C-7 | `text/translation_domains.py`, `core/config.py` (`load_system_prompt`), `pipeline/support.py`, `pipeline/glossary_phase.py`, `pipeline/output_validation.py`, `pipeline/display_hygiene.py`, `pipeline/quality_gate.py` (домен, theology-поля, scripture → numbered_citation), `validation/quality_gate_audit.py`, `validation/acceptance.py` (theology-проверка), `validation/structural.py:197,206-209,520`, `validation/structural_checks.py:60,92-97,587-593`, `validation/profiles.py` (домен), `document/segments.py` (домен), `document/structure_repair.py:22,551`, `processing/preparation.py` (домен), `pipeline/contracts.py`, `_pipeline.py`, `setup.py`, `application_flow.py`, локали, `system_prompt.txt`, `example_*.txt`, `run_lietaer_validation.py` (theology), фикстуры late_phases и output_validation_characterization |
| P2 structure-remnants | `066/structure` | C-1, C-3, C-5, C-6, C-8, C-9 | `document/extraction.py`, `document/roles.py`, `document/structure_repair.py` (signal_only), `document/layout_cleanup.py`, `document/relations.py`, `document/semantic_blocks.py`, `document/segments.py` (ai-фаза/роль), `document/boundary_review.py`, `structure/validation.py`, `core/models.py`, `core/config_structure_sections.py`, `core/config_model_registry.py`, `core/config.py` (роль), `processing/preparation.py` (structure recovery), `processing/processing_service.py:426`, `ui/_app.py:339`, три файла промптов, `config.toml:120` |
| P3 validation-dead-paths | `066/validation` | C-2, C-4, C-10, FR-012 | `validation/structural_unit_alignment.py`, `structural_toc_signals.py`, `structural.py:567,757-870`, `structural_prep_snapshot_helpers.py`, `acceptance.py` (topology), `structural_checks.py` (topology), `structure/layout_signals.py`, `runtime/artifact_retention.py`, `core/config_runtime_sections.py:127-133`, `core/config.py:332`, `core/config_loader_layers.py:191`, `validation/profiles.py` (reader_verifier), `config.toml:81`, фикстуры structural_validation_characterization, новый гард-тест FR-012 |
| P4 generation-and-image | `066/generation` | B-1, B-2, B-3, C-11, C-12 | `generation/_generation.py`, `generation/search.py`, `image/shared.py`, `image/model_capabilities.py`, `image/generation.py`, `image/pipeline.py`, `.github/CODEOWNERS`, `docs/LOGGING_AND_ARTIFACT_RETENTION.md` (новое событие) |

## Changelog

- 2026-11-08 — **реализация четырьмя агентами в боковых worktree, слияние в `066/integration`**
  (P4 `8efa348`, P2 `0ae4286`, P1 `b157942`, P3 `fc7fd36`); конфликты в `processing/preparation.py`,
  `tests/test_preparation.py`, `tests/test_application_flow.py` (P1 и P2 убирали соседние токены ключа
  подготовки: оба удаления оставлены, `pk=4` не поднят — старые ключи содержали удалённые токены и
  отдаться не могут), `validation/structural.py` и `docs/LOGGING_AND_ARTIFACT_RETENTION.md` сведены
  оркестратором. Поправки к спеке по ходу: **C-4 отозвана** (см. находку); A-1 имела не одну, а три
  точки освобождения (`:849` и оба сборщика сэмплов); гард FR-005 строится не по заголовкам книг из
  профилей, а по заголовкам, title и авторам из DOCX корпуса (они в git) — «Making Versus Taking» в
  названии книги не встречается; поле `pdf_import/text_layer_quality.py:387` называет две книги в
  docstring как источник замера (Конституция VIII), это не правило — исключение SC-004.
- 2026-11-08 — P1 (`066/domain`, 6 коммитов `d5ac0a4..b613f68`): удалены C-7, A-1 (с двумя неучтёнными в
  спеке освобождениями в сборщиках сэмплов), A-4; ключ `heldout_money_sustainability_class` (A-2);
  оглавление и абзац *The Value of Everything* в промпт-примерах заменены вымышленными (A-3, A-6); гард
  FR-005 `tests/test_prompts_carry_no_corpus_literals.py` читает заголовки, title и авторов DOCX книг
  корпуса (падает на `b402b2d`); поля и проверка `theology_style_*` (T-2); ось `translation_domain`
  целиком вместе с `fixed_terms` запроса глоссария (поле всегда было пустым), `domain_terms` артефакта и
  `:td=` ключа подготовки (T-1); `scripture_reference*` → `numbered_citation*` (A-5). Промпты — прежние
  минус ровно 70 знаков секции домена: translate 6907/`fa3afff9…`, edit 4887/`41c6552c…`, toc
  5805/`6da3dbf8…`, audiobook 9982/`792cfe7e…` (вместо theology-строки). **SC-002: replay сборки четырёх
  книг третьего прогона до/после побайтно равен** (markdown, реестр, display, сэмплы); на корпусе A-1 —
  0 совпадений из 1358 проверок, A-4 — 0/1601, C-7 — 0/5839. Эталоны и скрипты —
  `D:\Temp\docxai-research\066-baseline\domain\`. Оставлено: `DocumentContextProfile.style_instructions`
  / `.glossary_terms` без производителя — хвост P5.
- 2026-11-08 — P2 (`066/structure`, 6 коммитов `85a3040..1761d03`): C-3 — удалены три промпта-сироты.
  C-8 — фабрики клиентов подготовки больше не читают `structure_recognition_model`. C-6 — удалены ключи
  `structure_validation_enabled` / `_save_debug_artifacts` / `_block_on_high_risk_noop` (с env и строками
  `config.toml`) и `write_structure_validation_debug_artifact`. C-5 — удалены шесть полей Stage-0 и
  `ParagraphDescriptor`. C-1 — удалена ось `structure_recovery` (`ai_first`/`signal_only`, фаза
  `ai_first_degraded_fallback`, `role_confidence == "ai"`, токены `sr`/`srm` ключа подготовки);
  `layout_cleanup.py:85` — спека ошиблась: локальный `signal_only` там живой переключатель flag/remove,
  переименован в `flag_only`. C-9 — роль переименована в `boundary_review`, legacy-ключ
  `[structure_recognition].model` и env `DOCX_AI_STRUCTURE_RECOGNITION_MODEL` не читаются (старые имена —
  в уже существующих таблицах удалённых ключей, WARNING `legacy_model_config_key_detected`; событие
  `legacy_model_config_source_used` удалено — у него не осталось производителя). **SC-003: snapshot
  четырёх профилей до/после побайтово равны**; полный дамп продуктовой подготовки (абзацы, отношения,
  отчёты, сегменты, задания) отличается только шестью удалёнными полями C-5 (2034/2187/1770/1417
  абзацев), 0 прочих расхождений — `D:\Temp\docxai-research\066-baseline\structure\<profile>.deep.*`.
- 2026-11-08 — P3 (`066/validation`, 6 коммитов `d6b96c7..445502a`): C-2 — удалены ветки
  topology/document_map в `validation/` (чтение четырёх неэмитируемых событий, `topology_unit`,
  детекторы проекции, `structure/layout_signals.py`, `DOCUMENT_TOPOLOGY_MAX_*`) и мёртвые аргументы
  `document_map=None, topology_projection=None` на вызове шлюза; из `preparation_diagnostic_snapshot`
  ушли 26 ключей (`ai_*`, `ai_first_degraded`, `structure_ai_attempted`, `fallback_*`, `document_map_*`,
  `document_topology_*`, счётчики `structure_*` фолбэка, `topology_*`) — на четырёх профилях все держали
  нейтральные значения, эталоны `D:\Temp\docxai-research\066-baseline\validation\`. C-10 — из 15
  записей оставлены 2, которые производит `preparation._REASON_LABELS`. **C-4 не выполнена — находка
  отозвана.** FR-012 — `tests/test_config_keys_are_read.py` (AST по полям `AppConfig`, два направления,
  третий тест ловит устаревшие записи allow-list): на `b402b2d` с пустым allow-list ловит C-1, C-2, C-6,
  C-8, C-12 и новые находки `default_model`, `model_options`, `validation_model`, `reconstruction_model`
  (нечитаемые плоские копии `models.*`, вне scope) и `document_context_prompt` (мёртвый fallback в
  `pipeline/setup.py`/`support.py` — хвост P5). Введён WARNING `config_key_ignored`: ключи верхнего
  уровня `config.toml`, которые не прочитал ни один резолвер (раньше принимались молча).
- 2026-11-08 — P4 (`066/generation`, 5 коммитов `f7d6017..36d21d5`): B-1 — снятие необязательного
  параметра после отказа провайдера идёт через один помощник `image/shared.py::drop_rejected_optional_param`
  и пишет WARNING `model_call_param_dropped` `{param, model, stage, error_code}` на всех трёх текстовых
  путях (Responses, Chat Completions, Anthropic Messages); памяти между вызовами нет. B-2 —
  `accepts_response_format`, ветка `response_format` и два retryable-входа удалены. B-3 — таблица
  алиасов Anthropic заменена правилом формы (префикс `anthropic:`/`anthropic/` снимается, точка между
  цифрами → дефис). C-11 — `generation/search.py` удалён с CODEOWNERS; новый гард — CODEOWNERS не
  называет несуществующих путей. C-12 — override удалён; **наблюдение:** бюджет документа по картинкам
  всегда выводится как n × (per_image + 1) и потому срабатывает только при перерасходе сверх доли
  одной картинки — тест остановки следующих картинок переписан на живой ключ с перерасходом анализа
  (это территория спеки 062, здесь записано). Исключения SC-004: docstring `model_capabilities.py:4,20,38`,
  OpenRouter-id `config.toml:109`.
- 2026-11-08 — P5, хвосты после слияния (`066/cleanup`, 5 коммитов `fcf83c6..f395158`, влиты `96b1a92`):
  в `quality_gate.py` удалены `topology_projection_supported` с меткой `topology_projection`, basis
  `topology_unit` и семь константных ключей отчёта (`structure_unit_total_count`, `document_map_toc_*`,
  `topology_*`, `document_map_compound_toc_split_hint_count`); удалены чтения никогда не эмитируемого
  события `reconciliation_report_saved` и ключи snapshot `outline_coverage_ratio`, `front_matter_leaks`,
  `front_matter_body_advisories`, `targeted_recall_invoked`, поля `document_map_present` /
  `outline_coverage_ratio` у `StructureValidationReport`; константы `toc_body_concat_structure_detected` /
  `toc_body_concat_gate_source = "legacy_markdown"` убраны из отчёта, метрик, проверок и раннера; из
  раннера убраны шесть счётчиков `ai_*_count`; удалён мёртвый fallback `document_context_prompt` из
  app_config (`UNPRODUCED_ALLOWED` пуст); удалены `DocumentContextProfile.style_instructions` /
  `glossary_terms` с `DOCUMENT_GLOSSARY_SECTION_HEADER` и `DEFAULT_GLOSSARY_PROMPT_MAX_CHARS`
  (`render_glossary_prompt_section` остался — его единственный потребитель глоссарий прогона). SC-003:
  четыре профиля против `fc7fd36` отличаются только шестью удалёнными ключами snapshot
  (`D:\Temp\docxai-research\066-baseline\cleanup\`). Оркестратор: описание секции контекста в
  `system_prompt.txt:19` больше не обещает «стилевые указания» (`ba98c25`; пины промптов не изменились —
  необязательная секция в них не входит); база pyright в главном дереве 192 → 168 (мёртвый код уносил
  с собой 24 ошибки типов). Оставлено с обоснованием: константные метки `*_gate_source =
  "legacy_markdown"` живых детекторов (`bullet_heading`, `page_placeholder`, `residual_bullet_glyph`,
  `mixed_script`) — провенанс, не остаток фичи; `tests/fixtures/money_gemini_passthrough_fixture.json` —
  записанный прогон-вход, не эталон вывода.
- 2026-11-08 — спека создана по сплошному обходу `src/` после вопроса владельца о «доменном
  глоссарии». Решения владельца того же дня: ручного входа в глоссарий не будет; домен удаляется.
