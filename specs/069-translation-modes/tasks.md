# Tasks: режимы перевода «Стандарт» и «Качество» с оценкой цены при загрузке

**Spec**: [spec.md](spec.md) | **Plan**: [plan.md](plan.md) (раздел «Порядок реализации: пакеты работ») |
**Контракты**: [contracts/](contracts/) | **Данные**: [data-model.md](data-model.md), [research.md](research.md) |
**Проверка**: [quickstart.md](quickstart.md)

Tier: полный цикл (Конституция, принцип III). Задачи сгруппированы по пакетам работ WP-0…WP-9; порядок внутри пакета
всегда один: (A) характеристические / золотые тесты того, что НЕ должно измениться → (B) падающие тесты нового поведения
(анти-вакуум: у каждого указано, чем доказано, что он падает без правки) → (C) реализация → (D) каноническая проверка
пакета. Пакет владеет ТОЛЬКО перечисленными у него файлами; правка вне перечня запрещена (план, «Конституция VI»).

## Формат и общие правила

- `T<пакет>.<номер>`; `[P]` — можно делать параллельно с соседними задачами того же пакета (разные файлы, нет зависимости).
  Между пакетами параллельность задана волнами (ниже).
- **Каноническая проверка пакета** — всегда одна команда на один selector, selector ДО опций pytest:
  `wsl.exe -d Debian --cd "D:\Temp\claude\wt-069-<slug>" -- bash scripts/test.sh <selector> -q`
  (в боковом worktree `.venv` — симлинк на главное дерево; без него `scripts/test.sh` не найдёт активатор). Из Git Bash
  `$VAR` на границе `wsl.exe` схлопывается — только литеральные пути, без циклов `for`. Голый `python` / `.venv-win` /
  `py -m pytest` запрещены (debug-путь допустим только с пометкой `debug-only`). Если вывод оборван — это сначала
  проблема транспорта; сужать до node selector, не расширять.
- **Тесты истории** (`test_spec_status_consistency` и т.п.) в боковом worktree пропускаются; они проверяются только в
  главном дереве (раздел «Слияние и приёмка»). `git` в боковом worktree под WSL не работает — коммиты и `git diff --check`
  делаются из Windows-стороны (Git Bash) в worktree, не через `wsl.exe`.
- **Конституция VII / гард 066:** в тестах и промптах нет ни текста книг, ни литералов конкретных книг, ни словарей слов;
  примеры — вымышленные, той же ФОРМЫ. **VIII:** утверждения о коде сверять на текущем `main`, не по памяти плана.
- **LF** во всех новых файлах; после правок `git diff --check`. Полные тексты в лог не пишутся (только в артефакты).
- Тема коммита пакета: `spec 069: <что сделано>` (это работа по спеке 069; статус спеки обновляет оркестратор вместе с
  первым слиянием, чтобы `test_spec_status_consistency` не упал).
- Не изобретать работу вне плана. Неясное оформлено задачей «уточнить» (`[?]`) с вопросом; агент пакета не гадает, а
  возвращает вопрос оркестратору.

## Волны и зависимости

```text
волна 1 (параллельно, файлы не пересекаются):  WP-1  WP-2  WP-3  WP-4  WP-5  WP-7      (WP-0 — параллельно, вне репо)
волна 2:  WP-6  ← слиты WP-1, WP-2, WP-3, WP-4, WP-5      WP-8 ← слиты WP-1, WP-3, WP-7
волна 3:  WP-9  ← слиты WP-1, WP-3, WP-6, WP-7, WP-8
приёмка:  полный прогон в главном дереве → ревью Codex → слияние в main → FR-008 (платно)
```

Критический путь: **WP-5 → WP-6 → WP-9** (WP-6 ждёт самого длинного из пакетов волны 1 — общий `block_execution.py` и пять
зависимостей; WP-9 ждёт WP-6 и WP-8). Короткие цепочки: WP-1/WP-3/WP-7 → WP-8 → WP-9. Блокер О-4 для WP-5 снят (T5.0
закрыта 2026-11-09).

---

## WP-0. Замер Haiku на шлифовке (необязательно, не код)

**Ветка**: нет (вне репозитория) | **Worktree**: нет; данные в `D:\Temp\docxai-research\069-wp0\` | **Агент**: Sonnet |
**Зависит от**: ничего | **Стоимость**: ≈ 0,06–0,12 $ — только после согласия владельца; можно пропустить целиком.

- [ ] **T0.1** Получить согласие владельца на сумму ≈ 0,06–0,12 $ (или зафиксировать «пропускаем»; тогда множитель Haiku
  = 3,0 из research R2 остаётся «предварительным», T0.2–T0.3 не выполняются). Done: ответ владельца записан оркестратором.
- [ ] **T0.2** DEBUG-ONLY харнес шлифовки (`polish_runner.py` + запись `responses.create` как в `reasoning_runner.py` из
  каталога данных bake-off) на двух главах bake-off: Haiku без параметра и с `effort=low`. По каждому ответу записать вывод,
  рассуждение, статус, лимит. Done: таблица в `D:\Temp\docxai-research\069-wp0\`, шаги помечены `debug-only`.
- [ ] **T0.3** Вывод: множитель Haiku (подтверждение 3,0 или иное число) и ответ «рассуждает ли Haiku по умолчанию через
  OpenRouter». Done: итог передан оркестратору; если число ≠ 3,0 — оркестратор правит `output_budget.py` отдельной
  задачей WP-2 (T2.7a), а не агент WP-0.

---

## WP-1. Конфиг и единое разрешение режима (FR-001 ядро)

**Ветка**: `069/translation-modes-config` | **Worktree**: `D:\Temp\claude\wt-069-config` | **Агент**: Sonnet |
**Сначала слиты**: ничего (волна 1) | **Владеет**: `src/docxaicorrector/core/translation_modes.py` (нов.),
`core/config.py`, `core/config_loader_layers.py`, `resources/config.toml`, `validation/profiles.py`,
`corpus_registry.toml`, `tests/test_translation_modes.py` (нов.), `tests/test_config.py`,
`tests/test_real_document_validation_corpus.py`.
Контракты: `contracts/translation-modes-config.md`, `data-model.md`.

**A. Характеристические тесты**
- [ ] **T1.1** В `tests/test_translation_modes.py` (нов.) и `tests/test_config.py`: зафиксировать, что для `edit` и
  `audiobook` результат разрешения — `None`, а `app_config` побайтно прежний после `apply_…`; что `load_app_config` без
  раздела `[translation_modes]` даёт прежние значения всех существующих полей (снимок текущего вывода). Done: тесты
  зелёные на `main` ДО правки кода (запустить и записать результат).

**B. Падающие тесты нового поведения**
- [ ] **T1.2** В `tests/test_translation_modes.py`: контракт TOML + env (env побеждает TOML, правило 066:
  `DOCX_AI_TRANSLATION_MODE_DEFAULT`, `DOCX_AI_TRANSLATION_MODES_<MODE>_<FIELD>`); неизвестный ключ в
  `[translation_modes.quality]` → `config_key_ignored`; неизвестный режим → ошибка загрузки (не молчаливый откат);
  невалидная модель/интенсивность/рассуждение → ошибка. Анти-вакуум: модуля `core/translation_modes.py` нет — на `main`
  `ImportError`; после создания пустого модуля каждый тест падает на `AttributeError`/`AssertionError` до реализации.
- [ ] **T1.3** Резолвер `resolve_effective_translation_config`: `standard`/`quality` побеждают явные `requested_model` /
  `requested_intensity` с WARNING `translation_mode_overrides_setting` (имена полей и `origin` `ui` / `run_profile:<id>`);
  `single` = прежние модель/интенсивность, без рассуждения, без второго прохода; профиль без поля → `translation_mode_default`;
  `edit`/`audiobook` → `None`. Анти-вакуум: падает, пока резолвер не пишет предупреждение (проверка по `caplog`).
- [ ] **T1.4** `tests/test_real_document_validation_corpus.py`: гард «каждый translate-профиль `corpus_registry.toml`
  объявляет `translation_mode` явно»; профили `ui-parity-translate-benchmark-standard` и `-quality` существуют как копии
  `ui-parity-translate-benchmark-advisory-image-safe-no-cleanup` и различаются только режимом; все 17 прежних
  translate-профилей = `single`. Анти-вакуум: гард падает на текущем реестре (ни у одного профиля поля нет).
- [ ] **T1.5** `RunProfile.translation_mode` (`standard|quality|single`, `_optional_choice`) и `resolve_runtime_resolution`
  доносят эффективные поля в `runtime_overrides` / `ResolvedRuntimeConfig`. Анти-вакуум: падает без поля в `RunProfile`.

**C. Реализация**
- [ ] **T1.6** Создать `core/translation_modes.py` (`TranslationModesConfig`, `load_translation_modes`,
  `resolve_effective_translation_config`, `apply_effective_translation_config`; чистый модуль, без Streamlit и сети),
  поля `translation_mode_default` / `translation_modes` в `core/config.py`, сборка payload в
  `core/config_loader_layers.py`, разделы `[translation_modes.standard|quality]` и `translation_mode_default` в
  `resources/config.toml` (значения режимов — по `contracts/translation-modes-config.md`). Done: T1.2, T1.3 зелёные.
- [ ] **T1.7** `validation/profiles.py`: поле `RunProfile.translation_mode`, разрешение через
  `core/translation_modes.resolve_effective_translation_config` (единственная функция, `origin = run_profile:<id>`).
  Done: T1.5 зелёный.
- [ ] **T1.8** `corpus_registry.toml`: `translation_mode = "single"` у 17 translate-профилей; два новых профиля FR-008.
  Done: T1.4 зелёный.

**D. Проверка**
- [ ] **T1.9** `... bash scripts/test.sh tests/test_translation_modes.py -q`, затем отдельными командами
  `tests/test_config.py -q` и `tests/test_real_document_validation_corpus.py -q`. Done: зелёные; `git diff --check` чист.

---

## WP-2. Профиль запроса, матрица рассуждения, бюджеты вывода (FR-003 генератор, FR-006)

**Ветка**: `069/request-profile` | **Worktree**: `D:\Temp\claude\wt-069-request-profile` | **Агент**: Opus (правила
генератора) | **Сначала слиты**: ничего (волна 1) | **Владеет**: `generation/_generation.py`,
`generation/output_budget.py` (нов.), `image/shared.py`, `text/glossary_pass.py`,
`tests/test_generation_request_profile.py` (нов.), `tests/test_output_budget.py` (нов.), `tests/test_glossary_pass.py`.
Контракты: `contracts/reasoning-api-matrix.md`.

**A. Золотые тесты SC-006 (ДО правки кода)**
- [ ] **T2.1** В `tests/test_generation_request_profile.py` зафиксировать байты запроса: `_build_request_kwargs`, запрос
  `_recover_from_persistent_empty_response` и запрос лестницы (`_attempt_degradation_ladder` → `_ladder_model_answer`) для
  `edit`, `audiobook` и `translate` БЕЗ профиля (Responses, Chat Completions/OpenRouter, нативный Anthropic) — снимок
  словарей kwargs. Done: тесты зелёные на `main` без единой правки генератора; результат записан (это и есть доказательство
  «байты прежние до правки»).
- [ ] **T2.2** [P] В `tests/test_output_budget.py` и `tests/test_glossary_pass.py`: лимиты вывода при m = 1 на длинах
  0 / 383 / 384 / 6 000 / 12 288 / 20 000 равны прежним значениям `_estimate_max_output_tokens`; `glossary_max_output_tokens`
  при прежних аргументах равен прежнему; значение константы `_LADDER_BUDGETABLE_SOURCE_CHARS` = 12 288. Done: зелёные на
  `main`.

**B. Падающие тесты нового поведения**
- [ ] **T2.3** `GenerationRequestProfile` (frozen; `reasoning_effort`, `output_budget_multiplier`, `usage_stage`) и
  аргумент `request_profile` у `generate_markdown_block` / `request_text_completion`: Responses несёт
  `reasoning={"effort": e}` при профиле и не несёт без; Chat — `extra_body.reasoning`. Анти-вакуум: падает на `main`
  (`TypeError` на неизвестный аргумент / нет ключа в kwargs).
- [ ] **T2.4** Синтетический отказ провайдера `Unsupported parameter: 'reasoning'` снимает параметр и пишет WARNING
  `model_call_param_dropped` — и на Responses, и на Chat (вложенный `extra_body.reasoning`); Anthropic — параметр не
  передаётся, WARNING `reasoning_effort_not_supported_for_provider` ровно один раз на пару (модель, уровень) за процесс.
  Анти-вакуум: Chat-вариант падает, пока `drop_rejected_optional_param` не умеет вложенный ключ.
- [ ] **T2.5** Профиль протащен до восстановления пустого ответа, лестницы деградации (в т.ч. вложенный
  `generate_markdown_block` внутри `_ladder_model_answer`) и до стадии учёта (`usage_stage` вместо жёсткого
  `text_generation`). Анти-вакуум: по одному тесту на каждую точку; каждый падает, если протаскивание в этой точке убрать
  (проверить выбросом передачи в рабочей копии и вернуть).
- [ ] **T2.6** Лимиты при m = 3 равны ожидаемым (`ceil(base * m)`, потолок `_MODEL_OUTPUT_TOKEN_CEILING`);
  `_ladder_budgetable_source_chars(1) == 12 288`, для m = 3 — `CEILING * 3 // (4 * 3)`; `glossary_max_output_tokens(...,
  multiplier=3)` → 3 072 и 16 384 для `required`/`optional` (research R2; О-5 вместо замера Haiku); неизвестная модель → 1,0;
  таблица множителей v1 по FR-006 (flash-lite 1,0; gemini-3.7-flash 1,0; gemini-3.8-flash 1,0; claude-haiku-5.5 3,0 —
  предварительно). Анти-вакуум: падает на `main` (нет `output_budget.py`, нет аргумента `multiplier`).

**C. Реализация**
- [ ] **T2.7** `generation/output_budget.py` (нов., `MODEL_OUTPUT_BUDGET_MULTIPLIERS` с комментарием происхождения каждого
  значения), `_estimate_max_output_tokens(target_text, multiplier=1.0)`, `_ladder_budgetable_source_chars(m)`,
  `glossary_max_output_tokens(entry_count, *, multiplier=1.0)` в `text/glossary_pass.py`. `_boost_request_output_budget` не
  менять. Done: T2.2, T2.6 зелёные.
- [ ] **T2.7a** [?→по итогам WP-0] Если WP-0 дал множитель Haiku ≠ 3,0 — поправить значение и комментарий происхождения.
  Done: тест T2.6 обновлён тем же коммитом. Иначе задача пропускается.
- [ ] **T2.8** `GenerationRequestProfile` и протаскивание в `_build_request_kwargs`, `_call_responses_create`
  (`reasoning` в `retryable_optional_params`), `_call_chat_completions_create` (`extra_body.reasoning`), нативный Anthropic
  (без параметра + однократный WARNING), `_recover_from_persistent_empty_response`, `_attempt_degradation_ladder` →
  `_ladder_translate_unit` → `_ladder_model_answer`, `_call_markdown_request_with_sdk_fallback` (стадия учёта из профиля).
  `image/shared.py::drop_rejected_optional_param` учится снимать вложенный `extra_body.reasoning`
  (`removable_params` += `"reasoning"`). Сервисные вызовы проверки границ и картинок профиль не получают. Done: T2.3–T2.5
  зелёные, T2.1 всё ещё зелёный.

**D. Проверка**
- [ ] **T2.9** Отдельными командами: `tests/test_generation_request_profile.py -q`, `tests/test_output_budget.py -q`,
  `tests/test_glossary_pass.py -q`. Done: зелёные; золотой T2.1 зелёный ДО и ПОСЛЕ (оба результата приложены к отчёту пакета).

---

## WP-3. Учёт: рассуждение, кеш, стадия `literary_polish`, область счётчиков (FR-003 учёт, FR-004 (6))

**Ветка**: `069/accounting` | **Worktree**: `D:\Temp\claude\wt-069-accounting` | **Агент**: Sonnet | **Сначала слиты**:
ничего (волна 1) | **Владеет**: `core/model_accounting.py`, `tests/test_model_accounting_069.py` (нов.).
Ограничение: `model_accounting` НИКОГДА не получает оценочных цифр (`core/model_accounting.py:12-22`, Anti-regression 4).

**A. Характеристические тесты**
- [ ] **T3.1** В `tests/test_model_accounting_069.py`: снимок текущего вывода `ModelCallUsage` / `_StageTotals` /
  `stages` на существующих стадиях (`text_generation`, `glossary_extraction`) для набора синтетических ответов Responses и
  Chat без новых полей. Done: зелёный на `main` до правки.

**B. Падающие тесты**
- [ ] **T3.2** `reasoning_tokens` читается из Responses (`usage.output_tokens_details.reasoning_tokens`) и Chat
  (`usage.completion_tokens_details.reasoning_tokens`); ответ без поля → `None`, а `reasoning_unreported_call_count += 1`
  (не 0). Анти-вакуум: тест падает, если реализация подставляет 0 (проверка `is None` и счётчик).
- [ ] **T3.3** Поля кеша `cached_tokens`, `cache_write_tokens`, `cache_discount_usd` читаются как отданы провайдером,
  суммируются по стадии; отсутствие → «неизвестно» (`cache_fields_reported_call_count` не растёт). Анти-вакуум: падает на
  `main` (полей нет).
- [ ] **T3.4** Стадия `literary_polish` присутствует в `stages` отдельно от `text_generation`.
- [ ] **T3.5** `pass_counter_scope("literary_polish")`: disposition / повторы / путь API / удаления текста, записанные
  внутри области, попадают в раздел `literary_polish` снимка и НЕ меняют общие счётчики; вложенность областей; выход по
  исключению восстанавливает область. Анти-вакуум: падает без области (общие счётчики изменились бы).

**C. Реализация**
- [ ] **T3.6** Поля `ModelCallUsage` и `_StageTotals`, чтение usage из обоих API, стадия `literary_polish`,
  `pass_counter_scope`, раздел `literary_polish` снимка. Done: T3.2–T3.5 зелёные, T3.1 зелёный.

**D. Проверка**
- [ ] **T3.7** `... bash scripts/test.sh tests/test_model_accounting_069.py -q`; затем (одним selector) существующие тесты
  учёта по `grep -l model_accounting tests/` — каждый файл отдельной командой. Done: зелёные.

---

## WP-4. Предикаты отката шлифовки (FR-004 (4))

**Ветка**: `069/polish-checks` | **Worktree**: `D:\Temp\claude\wt-069-polish-checks` | **Агент**: Sonnet |
**Сначала слиты**: ничего (волна 1) | **Владеет**: `text/polish_checks.py` (нов.), `tests/test_polish_checks.py` (нов.).
Чистые функции, без Streamlit и сети; тексты книг в тестах запрещены (Конституция VII) — только вымышленные пары формы
срабатываний C.

**A. Характеристика «молчит на хорошей правке»**
- [ ] **T4.1** В `tests/test_polish_checks.py`: набор вымышленных хороших правок (стилистика, перестановка слов, замена
  синонима; «•» → «-»; длина 0,82 и 1,43) — ни один предикат не срабатывает. Эти тесты пишутся ПЕРВЫМИ и считаются
  контрактом «не ловить хорошее»; пока модуля нет, они падают на `ImportError` — после реализации обязаны быть зелёными.

**B. Падающие тесты по предикатам** (каждый — отдельный тест на свою форму; анти-вакуум: заглушка `return False` в
каждом предикате роняет соответствующий тест)
- [ ] **T4.2** P1 числа (нормализованные токены): «23 → 32», «1.5 → 15», «23 → двадцать три» ловятся.
- [ ] **T4.3** P2 новое слово не целевого письма (вымышленное «will»-подобное слово); P2′ исчезнувшее слово не целевого
  письма (О-2); для целевого латинского письма (en) предикаты работают симметрично; URL и e-mail токены игнорируются.
- [ ] **T4.4** P3 смешанный алфавит внутри слова; P4 префикс пункта после нормализации маркеров доставки (О-3: «•» → «-»
  НЕ ловится, «2.» → «1.» ловится); P5 потерянная сноска; P6 длина вне [0,70; 1,50] (0,69 и 1,51 ловятся).
- [ ] **T4.5** Сводная функция проверки абзаца возвращает причину отката (`rollback_reason`) из фиксированного набора,
  совпадающего с перечислением в `contracts/literary-polish-rollbacks.schema.json`. Анти-вакуум: тест сверяет множество
  причин с enum схемы и падает при расхождении.

**C. Реализация**
- [ ] **T4.6** `text/polish_checks.py`: предикаты P1–P6, P2′ и сводная функция; без словаря числительных (запись числа
  словами — консервативный откат). Done: T4.1–T4.5 зелёные.

**D. Проверка**
- [ ] **T4.7** `... bash scripts/test.sh tests/test_polish_checks.py -q`. Done: зелёный; `tests/test_prompts_carry_no_corpus_literals`
  (если затрагивает tests) проверяется в главном дереве при приёмке.

---

## WP-5. Примечания в конце главы: запрос и шлюз (FR-005)

**Ветка**: `069/notes-chains` | **Worktree**: `D:\Temp\claude\wt-069-notes-chains` | **Агент**: Opus (правило шлюза с
вычитанием из счёта дефектов) | **Сначала слиты**: ничего (волна 1; О-4 решено, T5.0 закрыта) |
**Владеет**: `pipeline/quality_gate.py`, `pipeline/output_validation.py`, `pipeline/block_execution.py` (ТОЛЬКО
`_build_block_apparatus_prompt` и его константы), `resources/prompts/operation_translate.txt`,
`tests/test_spec_069_notes_gate.py`, `tests/test_spec_069_notes_apparatus.py` (оба нов.). Пакет ДОЛЖЕН быть слит в
интеграционную ветку РАНЬШЕ WP-6 (общий `block_execution.py`).

**0. Блокер и уточнение**
- [x] **T5.0** Подтверждение О-4 — ЗАКРЫТО оркестратором 2026-11-09: правка запроса и правила 12 общая для всех
  режимов, включая `single` (спека, Changelog «Решения оркестратора по отклонениям плана»; SC-006 и Anti-regression 1
  уточнены, `plan.md` «Отклонения от спеки» обновлён). Пакет стартует без ожидания.
- [ ] **T5.0a** [?] Имена тестовых файлов. План и quickstart называют `tests/test_spec_069_notes_gate.py` /
  `tests/test_spec_069_notes_apparatus.py` «по фактическому расположению тестов шлюза и исполнения блока» и оставляют
  окончательные имена этому tasks.md. Решение этой версии: имена оставить как в плане (рядом с
  `tests/test_gate_detectors_stage2.py` и `tests/test_spec_067_apparatus_in_body.py`); если агент находит там уже
  принятое иное соглашение — вернуть вопрос, не переименовывать молча.

**A. Характеристика (ДО правки)**
- [ ] **T5.1** В `tests/test_spec_069_notes_gate.py` и `…_apparatus.py` зафиксировать прежнее поведение: обычный абзац с
  URL и 40+ словами латиницей даёт образец `untranslated_body` как раньше; порог образца (280 символов, 30 слов) и документа
  (2 000 символов, 2 %) прежние; байты `_build_block_apparatus_prompt` на блоке БЕЗ цепочки примечаний (и текст
  `operation_translate.txt`, кроме правила 12) прежние — золотой тест О-4. Плюс прогон соседних наборов
  `tests/test_gate_detectors_stage2.py`, `tests/test_spec_067_apparatus_in_body.py` на `main` (результат записан). Done:
  зелёные до правки.

**B. Падающие тесты**
- [ ] **T5.2** Шлюз: цепочка «ссылки + один английский комментарий ≥ 280 символов» даёт образец длиной ТОЛЬКО комментария
  (`char_count` = длина непереведённой части). Анти-вакуум: сейчас образец равен всей длине абзаца или отсутствует —
  тест падает на `main`.
- [ ] **T5.3** Шлюз: цепочка только из ссылок с URL и 60+ словами — образца НЕТ. Анти-вакуум: сейчас образец есть
  (ветка URL, `quality_gate_text_detectors.py:76-78`) — тест падает на `main`.
- [ ] **T5.4** Анти-вакуум по VII (правило, вычитающее из счёта дефектов): цепочка с непереведёнными английскими
  определениями (форма D, вымышленная) продолжает давать образец, а документ — блокироваться выше порогов; настоящий
  непереведённый комментарий всё ещё считается. Этот тест обязан пройти и до, и после правки (защита от обхода шлюза) и
  дополнительно падать на заведомо сломанной реализации «шлюз игнорирует цепочки целиком» (проверить временной заглушкой).
- [ ] **T5.5** Запрос: для абзаца-цепочки в маркерном режиме раздел аппарата содержит строку «В абзаце
  [[DOCX_PARA_id]] авторский текст есть в примечаниях N, M: его переведите, ссылки и имена авторов в них оставьте»
  (номера — `notes_run_commentary_numbers`, per-entry форма 067); у абзаца из одних ссылок строки нет. Тест на вымышленном
  исходнике формы p0102–p0111: отметка 067 ставится, раздел уходит в запрос. Анти-вакуум: падает на `main`.
- [ ] **T5.6** Правило 12 `operation_translate.txt` содержит фразы «решайте по каждому примечанию, а не по абзацу целиком;
  имя автора — часть ссылки» (проверка по смыслу строки, без литералов книг).

**C. Реализация**
- [ ] **T5.7** `pipeline/output_validation.py`: части цепочки (`notes_run_untranslated_part`, записи-комментарии по
  per-entry-тесту 067). `pipeline/quality_gate.py` (сбор образцов, `:560-603`): образец цепочки из её непереведённой части;
  для прочих абзацев путь не меняется; пороги не менять. Done: T5.2–T5.4 зелёные.
- [ ] **T5.8** `_build_block_apparatus_prompt` (`block_execution.py:708-746`) и константы: строка про примечания;
  `operation_translate.txt`: правило 12. Правка файла `block_execution.py` — только в этой функции и её константах.
  Done: T5.5, T5.6 зелёные, T5.1 зелёный.

**D. Проверка**
- [ ] **T5.9** Отдельными командами: `tests/test_spec_069_notes_gate.py -q`, `tests/test_spec_069_notes_apparatus.py -q`,
  `tests/test_gate_detectors_stage2.py -q`, `tests/test_spec_067_apparatus_in_body.py -q`. Done: зелёные.
- [ ] **T5.10** (DEBUG-ONLY, после слияния; запускает оркестратор) офлайн-повтор `fr005_gate_replay.py` по quickstart §3:
  346–348 у Gemini-вариантов Money, ≈ 3 656 у D. Не доказательство канонического пути.

---

## WP-6. Второй проход «литературная шлифовка» в конвейере (FR-004)

**Ветка**: `069/literary-polish` | **Worktree**: `D:\Temp\claude\wt-069-literary-polish` | **Агент**: Opus |
**Сначала слиты в `069/integration`**: WP-1, WP-2, WP-3, WP-4, **WP-5 (раньше остальных — общий `block_execution.py`)** |
**Владеет**: `pipeline/literary_polish.py` (нов.), `pipeline/block_execution.py` (крюк, кеш промпта, профиль первого
прохода в `_generate_block_chunk`), `pipeline/contracts.py`, `pipeline/setup.py`, `pipeline/glossary_phase.py`,
`resources/prompts/operation_literary_polish.txt`, `runtime/artifact_retention.py`, `tests/test_literary_polish.py` (нов.),
`tests/test_document_pipeline.py`, тесты `glossary_phase` (существующий файл найти по `grep -l glossary_phase tests/`).
Контракты: `contracts/literary-polish-rollbacks.schema.json`, `contracts/events.md`, `data-model.md`. База ветки —
свежая `069/integration` со слитыми зависимостями.

**0. Уточнение**
- [x] **T6.0** Регистрация событий второго прохода — РЕШЕНО оркестратором 2026-11-09: если гард на зарегистрированные
  события (`_list_log_events.py` / `test_logging_*`) падает в ветке WP-6, WP-6 вносит в реестр событий ТОЛЬКО свои новые
  имена событий (точечная правка, без описаний); `docs/LOGGING_AND_ARTIFACT_RETENTION.md` и описание событий остаются за
  WP-9. Красным до WP-9 не держать.

**A. Характеристика (ДО правки)**
- [ ] **T6.1** В `tests/test_literary_polish.py` / `tests/test_document_pipeline.py`: прогон блока через ОБЫЧНЫЙ вход
  (`process_single_block`) с двойником генератора для `edit`, `audiobook`, `translate`/`single` — снимок доставленного
  текста, реестра, счётчиков disposition, числа вызовов генератора. Done: зелёные на текущей интеграционной ветке до
  правки (результат записан).
- [ ] **T6.2** [P] Кеш промпта: снимок `_get_cached_system_prompt` для существующих вариантов; `state` / `initialization`
  без новых полей — прежнее поведение. Done: зелёный до правки.

**B. Падающие тесты** (все через обычный вход блока с двойником генератора; анти-вакуум указан у каждого)
- [ ] **T6.3** Принятая шлифовка доставлена, и реестр, проекция аудиокниги и восстановление сносок видят ЕЁ текст.
  Анти-вакуум: падает без крюка (доставлен первый проход).
- [ ] **T6.4** Абзацы `omitted` / `source_restored` / `policy_kept_source` не отправлены и не изменены; абзац с долей
  букв целевого письма < 0,5 не отправлен (О-1, форма ссылки по D1 — вымышленный абзац); блок без маркеров с одним
  абзацем шлифуется, многоабзацный без маркеров — нет (`skipped_unmarked_block_count`). Анти-вакуум: падает без отбора
  `select_polish_paragraphs`.
- [ ] **T6.5** Каждый предикат P1–P6, P2′ → откат абзаца, строка артефакта `.run/literary_polish_rollbacks/<run_id>.jsonl`
  (валидна по JSON-схеме контракта), событие `literary_polish_paragraph_rolled_back` без текстов; несовпадение маркеров /
  порядка id → откат блока (`block_marker_mismatch`); ответ не `accepted` → `not_accepted`. Анти-вакуум: падает без отката.
- [ ] **T6.6** Исключение второго прохода → первый проход блока + WARNING `literary_polish_block_failed` (причина, класс
  ошибки, блок); `allow_controlled_source_fallback=False`, без лестницы. `LatePhaseStopped` (`BaseException`) во время
  шлифовки → первый проход доставлен, `state.stopped_during_polish = True`, прогон остановлен через `_emit_stopped(index+1)`,
  в том числе на ПОСЛЕДНЕМ блоке. Анти-вакуум: падает без флага `stopped_during_polish`.
- [ ] **T6.7** Счётчики disposition первого прохода одинаковы со шлифовкой и без; внутренние записи генератора идут в
  раздел `literary_polish` через `pass_counter_scope`; свои счётчики второго прохода (`sent_paragraph_count`,
  `accepted_paragraph_count`, `rolled_back_paragraph_count`, `rollback_reason_counts`, `block_rollback_count`,
  `failed_block_count`, `skipped_paragraph_counts`, `artifact_path`). Анти-вакуум: падает без `pass_counter_scope`.
- [ ] **T6.8** Кеш промпта: `literary_polish` и `default` — разные строки, `literary_polish` строится один раз
  (`state.polish_system_prompt`); промпт шлифовки содержит контекст документа и глоссарий прогона (операция `translate`
  в `build_system_prompt_arguments`). Контекст вызова: «до» — хвост доставленного текста предыдущего блока (О-7), «после» —
  пусто.
- [ ] **T6.9** `single` и `edit` не вызывают шлифовку; «Качество» — глоссарий и все вызовы первого прохода несут
  `reasoning.effort = low` и множитель модели (профиль первого прохода в `_generate_block_chunk` и `glossary_phase.py`);
  «Стандарт» — профиль первого прохода без рассуждения. Анти-вакуум: падает, пока профиль не передан.
- [ ] **T6.10** `runtime/artifact_retention.py`: `LITERARY_POLISH_ROLLBACKS_MAX_AGE_SECONDS` / `_MAX_COUNT` (7 дней, 400
  файлов, как `marker_attempts`), `prune_artifact_dir` вызывается после записи. Анти-вакуум: падает на `main`.
- [ ] **T6.11** Гард промптов: `operation_literary_polish.txt` содержит три правила (числа как в тексте; маркеры и номера
  пунктов не менять; фрагменты на другом письме не переводить и не транслитерировать) без литералов книг.

**C. Реализация**
- [ ] **T6.12** `pipeline/literary_polish.py` (`select_polish_paragraphs`, вызов, откат, сборка `MarkerPreservedBlockText`
  со старыми статусами, артефакт, события), `pipeline/contracts.py` (`state.polish_system_prompt`,
  `state.stopped_during_polish`, `initialization.polish_client` / `polish_model_id`, протокол `MarkdownGenerator` с
  `request_profile`), `pipeline/setup.py` (клиент второго прохода), `pipeline/glossary_phase.py` (профиль первого
  прохода). Done: T6.4–T6.7 зелёные.
- [ ] **T6.13** `pipeline/block_execution.py`: инжектируемый `literary_polish_fn`, крюк после `processed_block_status ==
  "valid"` и до `model_kept_apparatus`; пропуск для сквозных, `policy_kept_chunk`, `toc_dominant`, не-`valid`; ветка
  `literary_polish` в `_get_cached_system_prompt`; проверка флага `stopped_during_polish` в `run_block_processing_phase`;
  профиль первого прохода в `_generate_block_chunk`. Правки `_build_block_apparatus_prompt` НЕ трогать (владелец — WP-5).
  Done: T6.3, T6.6, T6.8, T6.9 зелёные.
- [ ] **T6.14** `resources/prompts/operation_literary_polish.txt`, `runtime/artifact_retention.py`. Done: T6.10, T6.11
  зелёные; T6.1, T6.2 всё ещё зелёные.

**D. Проверка**
- [ ] **T6.15** Отдельными командами: `tests/test_literary_polish.py -vv`, `tests/test_document_pipeline.py -q`, тесты
  `glossary_phase` (имя файла уточнить `grep`-ом), `tests/test_gate_detectors_stage2.py -q` и
  `tests/test_spec_067_apparatus_in_body.py -q` (проверка, что WP-6 не сломал WP-5). Done: зелёные; `git diff --check`.

---

## WP-7. Оценщик цены и прайс (FR-007 ядро)

**Ветка**: `069/cost-estimate` | **Worktree**: `D:\Temp\claude\wt-069-cost-estimate` | **Агент**: Sonnet | **Сначала
слиты**: ничего (волна 1) | **Владеет**: `pipeline/cost_estimate.py` (нов.), `pipeline/price_list.py` (нов.),
`resources/cost_estimate_coefficients.json` (нов.), `tests/test_cost_estimate.py`, `tests/test_price_list.py` (нов.).
Контракты: `contracts/cost-estimate.md`, `contracts/cost-estimate-snapshot.schema.json`. Модули без Streamlit и без
импорта `model_accounting`; таблица коэффициентов замораживается до FR-008.

**A. Характеристика**
- [ ] **T7.1** [P] В `tests/test_cost_estimate.py`: гард импорта — `pipeline/cost_estimate.py` и `price_list.py` не
  импортируют `streamlit` и `model_accounting` (проверка по AST/`sys.modules`). Анти-вакуум: проверить, что гард видит
  запрещённый импорт, подмешав его во временный модуль в тесте.

**B. Падающие тесты**
- [ ] **T7.2** Таблица v1 воспроизводит книги research R3 при прайсе 2026-11-09: RM «Стандарт» 1,22, Money «Стандарт»
  1,05, RM «Качество» 1,88, Money «Качество» 1,81 (допуск из контракта); регрессия формул (`contracts/cost-estimate.md`:
  якорь — форма документа для модели первого прохода `single`, прочие — отношение к якорю; О-8). Анти-вакуум: падает на
  `main` (нет модуля).
- [ ] **T7.3** Низ = верх для моделей без наблюдённой скидки (О-6; подпись «скидка не наблюдалась»); сценарий скидки только
  у flash-lite; пара языков вне таблицы → `coefficients_extrapolated` и подпись «приблизительно» (не молчаливый en→ru); без
  прайса → «цена неизвестна», не ноль; нативные `anthropic:`/`openai:` модели → «цена неизвестна» для их стадий; подпись «без
  картинок». Вывод валиден по `cost-estimate-snapshot.schema.json`.
- [ ] **T7.4** `tests/test_price_list.py`: кеш `.run/price_list/openrouter_models.json` свежий (< 24 ч) — сети нет (мок сети
  падает при вызове); кеш устарел → запрос с тайм-аутом 5 с; сеть упала → старый кеш с его датой + WARNING
  `price_list_fetch_failed`; нет кеша → `None`. Анти-вакуум: мок сети, вызванный при свежем кеше, роняет тест.

**C. Реализация**
- [ ] **T7.5** `resources/cost_estimate_coefficients.json` (версия `v1`, происхождение каждой записи), `pipeline/cost_estimate.py`
  (`EstimateInput`, `CoefficientTable`, `CostEstimate`, `estimate_text_stages`), `pipeline/price_list.py` (`get_price_list`).
  Прайс — `urllib.request` или `httpx` из `openai`, новых зависимостей нет. Без сети оценка ≤ 50 мс. Done: T7.2–T7.4 зелёные.

**D. Проверка**
- [ ] **T7.6** Отдельными командами `tests/test_cost_estimate.py -q` и `tests/test_price_list.py -q`. Done: зелёные.

---

## WP-8. UI, снимок оценки в результате, событие сравнения (FR-002, FR-007 UI)

**Ветка**: `069/ui-modes` | **Worktree**: `D:\Temp\claude\wt-069-ui-modes` | **Агент**: Sonnet | **Сначала слиты в
`069/integration`**: WP-1, WP-3, WP-7 | **Владеет**: `ui/_ui.py`, `ui/_app.py`, `ui/locales/ru.json`,
`ui/locales/en.json`, `processing/processing_runtime.py`, `pipeline/_pipeline.py`, `tests/test_ui_translation_modes.py`
(нов., `AppTest`), `tests/test_processing_runtime.py`, `tests/test_ui_i18n.py`. Layout — только штатные примитивы
Streamlit; никакого `use_container_width` (заменять на `width="stretch"`); CSS-селекторы по DOM не использовать.

**A. Характеристика (ДО правки)**
- [ ] **T8.1** `AppTest` для `edit`: прежние виджеты (селектор модели, интенсивность), кортеж `render_sidebar`,
  `_resolve_sidebar_settings` со старой формой — зафиксировать. Снимок `build_result_bundle` без новых аргументов и
  `bundle` без снимка оценки. Done: зелёные до правки.
- [ ] **T8.2** [P] Снимок перехода edit → translate → edit и применения рекомендации `ui/recommended_text_settings.py`:
  модель и интенсивность `edit` не меняются. Done: зелёный до правки.

**B. Падающие тесты**
- [ ] **T8.3** `AppTest`, `translate`: `st.radio` `sidebar_translation_mode` с двумя вариантами (`standard` по умолчанию,
  `quality`), подпись с ценой из сессии; селектора модели в «Дополнительно» и интенсивности нет; предупреждение о
  доступности модели проверяет обе эффективные модели режима. Анти-вакуум: падает на `main` (радио нет).
- [ ] **T8.4** До загрузки — без цены («цена появится после загрузки документа»); после подготовки — «≈ X–Y $»; без прайса
  — «цена неизвестна». Ключ сессии `(file_token, prepared_source_key, source/target, coefficients_version, price_list_date)`;
  смена любого компонента сбрасывает оценку.
- [ ] **T8.5** Единое разрешение: `ui/_app.py::main` зовёт `resolve_effective_translation_config(...)` с
  `requested_model=None`, `requested_intensity=None` для `translate` и `apply_…` к `app_config`; режим не утекает в
  `edit` (T8.2 остаётся зелёным).
- [ ] **T8.6** «Старт» замораживает снимок оценки выбранного режима (валиден по схеме); `build_result_bundle(...,
  cost_estimate_snapshot=None, cost_actual=None)` кладёт оба; экран результата показывает факт рядом со СВОЕЙ оценкой;
  bundle без снимка — без оценки (анти-вакуум: падает, если показывать текущую оценку вместо снимка).
- [ ] **T8.7** Событие `cost_estimate_vs_actual` рядом с `emit_run_model_accounting_event`: факт — из снимка учёта по
  стадиям `glossary_extraction` + `text_generation` + `literary_polish` (`cost_usd_reported_by_provider`),
  `relative_error_vs_upper = (факт − верх) / факт`, `within_range`; частичный/остановленный прогон → `run_complete: false` и
  ошибка не сравнивается. Анти-вакуум: падает на `main`.
- [ ] **T8.8** Локали ru/en: одинаковые ключи (`tests/test_ui_i18n.py`), новые строки режимов и цены.

**C. Реализация**
- [ ] **T8.9** `ui/_ui.py` (`render_sidebar`: радио режима, скрытие модели/интенсивности для `translate`, цена; кортеж растёт
  до 13 элементов, `translation_mode` последним), `ui/_app.py` (`_resolve_sidebar_settings` дополняет старые формы пустым
  режимом; единое разрешение; расчёт и хранение оценки в сессии; снимок при «Старт»; факт рядом на результате),
  `ui/locales/ru.json`, `ui/locales/en.json`. Done: T8.3–T8.5, T8.8 зелёные.
- [ ] **T8.10** `processing/processing_runtime.py` (`build_result_bundle` с двумя новыми аргументами), `pipeline/_pipeline.py`
  (событие `cost_estimate_vs_actual`). `model_accounting` не трогать. Done: T8.6, T8.7 зелёные; T8.1 зелёный.
- [ ] **T8.11** [?] Если на `AppTest` задержка одной перерисовки до появления цены окажется заметной — план называет запасной
  вариант «радио в основной области у кнопки Старт». Не переходить на него без вопроса оркестратору.

**D. Проверка**
- [ ] **T8.12** Отдельными командами: `tests/test_ui_translation_modes.py -vv`, `tests/test_processing_runtime.py -q`,
  `tests/test_ui_i18n.py -q`. Done: зелёные.
- [ ] **T8.13** Ручная проверка во встроенном браузере (Streamlit Layout Contract): «Перевод» → радио «Стандарт» /
  «Качество»; селектора модели нет; до загрузки без цены, после подготовки «≈ X–Y $», после прогона факт рядом с оценкой,
  подпись «без картинок»; «Редактирование» — как раньше. Done: описание результата в отчёте пакета (полный pytest после
  CSS/layout-правок не требуется).

---

## WP-9. Раннер, отчёт, документ логирования

**Ветка**: `069/runner-report` | **Worktree**: `D:\Temp\claude\wt-069-runner-report` | **Агент**: Sonnet | **Сначала
слиты в `069/integration`**: WP-1, WP-3, WP-6, WP-7, WP-8 | **Владеет**:
`tests/artifacts/real_document_pipeline/run_lietaer_validation.py`, `docs/LOGGING_AND_ARTIFACT_RETENTION.md`,
`tests/test_real_document_pipeline_validation.py`. Артефакты прогонов и `.run/` вне git; тексты книг в тестах нет.

**A. Характеристика (ДО правки)**
- [ ] **T9.1** В `tests/test_real_document_pipeline_validation.py` зафиксировать текущую форму отчёта раннера и
  `run_summary` (ключи, порядок секций) для прогона без режима. Плюс прогон гардов `test_logging_*` / `_list_log_events.py`
  (зелёные на слитой интеграционной ветке). Done: зелёные до правки.

**B. Падающие тесты**
- [ ] **T9.2** Отчёт несёт режим и эффективные модели/интенсивность/рассуждение ОБОИХ проходов в runtime-config и в
  `runtime_overrides` `run_summary`. Анти-вакуум: падает на текущей форме.
- [ ] **T9.3** `run_summary`: рассуждение и поля кеша по стадиям (`reasoning_unreported_call_count`,
  `cache_fields_reported_call_count`), строки `literary_polish_*`, путь артефакта откатов; копия файла в
  `runs/<run_id>/literary_polish_rollbacks.jsonl` (раннер изолирует `.run` прогона через `DOCX_AI_RUN_DIR`).
- [ ] **T9.4** Раннер считает ту же оценку ДО прогона (`cost_estimate`) и пишет сравнение `cost_estimate_vs_actual` после;
  события второго прохода попадают в `events.jsonl` (068 FR-002).
- [ ] **T9.5** Гард документа логирования: новые события (`literary_polish_paragraph_rolled_back`,
  `literary_polish_block_failed`, `cost_estimate_vs_actual`, `translation_mode_overrides_setting`,
  `reasoning_effort_not_supported_for_provider`, `price_list_fetch_failed`, `model_call_param_dropped` — полный перечень
  берётся из `contracts/events.md`) и семьи `.run/literary_polish_rollbacks/`, `.run/price_list/` зарегистрированы.

**C. Реализация**
- [ ] **T9.6** `run_lietaer_validation.py`: отчёт, `run_summary`, оценка до прогона и сравнение, копия артефакта откатов.
- [ ] **T9.7** `docs/LOGGING_AND_ARTIFACT_RETENTION.md`: события, семьи `.run/`, сроки (7 дней / 400 файлов), правило
  «полные тексты только в артефактах». Done: T9.2–T9.5 зелёные; `test_documentation_links` не затронут.

**D. Проверка**
- [ ] **T9.8** Отдельными командами `tests/test_real_document_pipeline_validation.py -q` и гарды логирования
  (`tests/test_logging_*.py`, по одному файлу на команду). Done: зелёные.

---

## Слияние и приёмка

Ведёт оркестратор. Интеграционная ветка — `069/integration` (план называет её `069-translation-modes`; рабочие ветки
пакетов `069/<slug>`). Агенты пакетов в интеграционную ветку не пишут.

- [ ] **TA.1** Порядок слияния в `069/integration`: сначала **WP-5** (раньше всех — общий `block_execution.py`; требует T5.0),
  затем WP-1, WP-2, WP-3, WP-4, WP-7 в любом порядке (файлы не пересекаются); затем WP-6 (после WP-1…WP-5); WP-8 (после
  WP-1, WP-3, WP-7); последним WP-9 (после WP-6 и WP-8). Каждый перенос пакета — на СВЕЖУЮ `069/integration`.
- [ ] **TA.2** После КАЖДОГО слияния — повторный полный прогон в ГЛАВНОМ дереве:
  `wsl.exe -d Debian --cd "D:\Work\Projects\DocxAICorrector" -- bash scripts/test.sh tests/ -q`
  (зелень пакета до переноса ничего не значит: AGENTS.md, 2026-08-08). Перед «всё зелёное» — `git status --porcelain`
  пуст (иначе локальный прогон не доказательство для CI); `git diff --check` чист. Оборванный вывод — сначала проблема
  транспорта: сужать до node selector, не запускать второй прогон параллельно.
- [ ] **TA.3** Гарды, которые нельзя проверить в боковом worktree, — в главном дереве на интеграционной ветке (каждый
  отдельной командой): `tests/test_spec_status_consistency.py` (статус спеки 069 обновляется вместе с первым слиянием; тема
  коммита называет `spec 069` только у работы по ней), `tests/test_where_we_are_freshness.py` (обновить
  `docs/WHERE_WE_ARE.md`), `tests/test_documentation_links.py`, `tests/test_prompts_carry_no_corpus_literals.py` (ни
  литералов книг, Конституция VII, в `operation_literary_polish.txt`, `operation_translate.txt`, тестах), базовая линия
  pyright — `tests/test_typecheck.py` (запускать ≥ 180 с; пустой вывод ≠ зависание; новых ошибок относительно baseline нет).
- [ ] **TA.4** Расширенное ревью Codex `gpt-6-astra`, `--sandbox read-only`, по рецепту AGENTS.md («Обязательная приёмка
  оркестратора»), ДО слияния в `main`: бинарь — самый свежий `codex.exe` в `%LOCALAPPDATA%\OpenAI\Codex\bin`
  (`Sort-Object LastWriteTime -Descending`); промпт файлом через stdin, ответ в файл, в фоне. Объём — все затронутые
  поверхности: каждый модуль с хотя бы одним изменённым hunk читается ЦЕЛИКОМ, плюс прямые вызывающие/вызываемые и тесты
  этих модулей (список из `git diff --stat <base>..<head>`). В промпте: base/head SHA, команды `git diff --stat` и
  `git log --oneline`, литеральные абсолютные пути поверхностей, путь к спеке, отдельным абзацем что измерено оператором
  (WSL ему закрыт); требовать `file:line`, частоту и чем она измерена, уверенность, вердикт последней строкой из
  фиксированного набора; формулировки без «атакуй/сломай». Каждую находку оркестратор проверяет по коду сам и
  приземляет: правка с тестом в той же ветке / запись в Changelog / отказ в Non-goals. Отчёт —
  `docs/reviews/CODEX_REVIEW_069_<YYYY-MM-DD>.md` (промпт + таблица «поднято / вердикт / замерено»).
- [ ] **TA.5** После правок по ревью — снова полный прогон в главном дереве (TA.2) и гарды (TA.3); затем слияние
  `069/integration` в `main` и push. Спека 069 не объявляется закрытой до этого шага.
- [ ] **TA.6** **FR-008 — платный замер** (только после слияния WP-1…WP-9, зелёного полного прогона, ревью Codex и
  ЯВНОГО подтверждения владельцем суммы ≈ 5–6 $). Коэффициенты `cost_estimate_coefficients.json` заморожены ДО прогонов
  (версия — в отчёте). Только канонический раннер, четыре прогона по `quickstart.md` §6
  (`scripts/run-real-document-validation.sh`; профили `ui-parity-translate-benchmark-standard` / `-quality` для
  `lietaer-pdf-full-benchmark` и `money-sustainability-pdf-full-heldout`; полный прогон — веха, не цикл настройки). При
  падении профиля сначала свежий run report: дословно `failed_checks` с `actual` / `threshold` и overage ratio, только
  потом гипотезы. Читать результаты по таблице quickstart §6 (SC-001…SC-005, причина скидки, Anti-regression 2).
  Слепое чтение SC-001/SC-002 — ОДИН рецензент в ОДНОМ раунде против замороженных якорей C, G-low-cons, A плюс 10
  повторённых абзацев. Done: результаты записаны в спеку как есть (в т.ч. SC-005 как проверяемая гипотеза); неудача
  критерия фиксируется, не ретушируется.
