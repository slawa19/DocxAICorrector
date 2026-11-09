# Implementation Plan: режимы перевода «Стандарт» и «Качество» с оценкой цены при загрузке

**Branch**: `069-translation-modes` (интеграционная; рабочие ветки пакетов — `069/wp-<N>-<slug>`) | **Date**: 2026-11-09 |
**Spec**: [spec.md](spec.md)

**Input**: `specs/069-translation-modes/spec.md` (после правок по ревью Codex, `docs/reviews/CODEX_REVIEW_069_SPEC_2026-11-09.md`);
замеры — [research.md](research.md); сущности — [data-model.md](data-model.md); контракты — [contracts/](contracts/);
проверка — [quickstart.md](quickstart.md).

## Summary

У операции `translate` появляются два режима, которые разрешает ОДНА функция для UI и раннера: «Стандарт» (первый проход
текущей моделью + второй проход `literary_polish` моделью Haiku внутри исполнения блока, с откатом по форме к первому
проходу) и «Качество» (один проход gemini-3.7-flash с `reasoning.effort = low` и сдержанной интенсивностью); `single` —
нынешний перевод для регрессионных профилей. Параметр рассуждения проходит матрицу API (Responses / Chat `extra_body` /
Anthropic — нет) и учитывается по стадиям; лимиты вывода получают множитель модели (1 для текущей); отдельный модуль
оценивает цену текстовых стадий по фиксированной версионированной таблице и датированному прайсу, снимок оценки едет с
результатом. Примечания-цепочки получают поабзацно-поэлементную правку запроса и шлюза (FR-005). Девять пакетов работ,
из них шесть параллельны с первого дня.

## Technical Context

**Language/Version**: Python 3.13 (WSL Debian, `.venv/bin/python`); Streamlit 1.64.0.

**Primary Dependencies**: `openai` SDK (Responses API + Chat Completions через OpenRouter), `anthropic` SDK (нативный путь),
Streamlit; новых зависимостей нет (прайс — `urllib.request` или уже установленный `httpx` из `openai`).

**Storage**: файлы `.run/` (вне git): `.run/literary_polish_rollbacks/<run_id>.jsonl`, `.run/price_list/openrouter_models.json`;
ресурс в git `src/docxaicorrector/resources/cost_estimate_coefficients.json`; результат прогона — `st.session_state` (bundle).

**Testing**: pytest через `bash scripts/test.sh` под WSL (канонический путь AGENTS.md); Streamlit `AppTest` для UI;
платный замер — `scripts/run-real-document-validation.sh` (FR-008, после согласия владельца).

**Target Platform**: WSL Debian (`/mnt/d/Work/Projects/DocxAICorrector`), UI Streamlit локально.

**Project Type**: одно Python-приложение (`src/docxaicorrector/`), тесты в `tests/`.

**Performance Goals**: оценка цены при загрузке — без сети ≤ 50 мс (чистая арифметика по подготовленному документу); прайс —
не дольше 5 с один раз в 24 ч, без сети — кеш; второй проход добавляет ≈ число LLM-блоков вызовов (C: 13 / 27 на главу).

**Constraints**: `single`, `edit`, `audiobook` — побайтно прежние запросы, промпты, бюджеты (SC-006; исключение — О-4);
`model_accounting` никогда не оценивает (`core/model_accounting.py:12-22`); никаких словарей и литералов книг (VII);
никаких ручек выбора модели, рассуждения, интенсивности в UI (D-3, правило владельца «полная автоматизация»).

**Scale/Scope**: книги 0,5 млн символов, 230–300 LLM-блоков; ≈ 30 файлов продукта, ≈ 12 новых тестовых файлов.

Неизвестных `NEEDS CLARIFICATION` нет; то, что на данных не определяется, перечислено в разделе «Что не определено».

## Constitution Check

### До дизайна

- **I/II — PASS.** Все проверки — `scripts/test.sh` через `wsl.exe -d Debian`; платный замер — канонический раннер. Скрипты
  `D:\Temp\docxai-research\069-plan\*.py` помечены DEBUG-ONLY и ничего не доказывают о продукте.
- **III — PASS, полный цикл.** Новый модуль (оценка цены, второй проход), новые контракты (режимы, рассуждение, артефакт
  откатов, снимок оценки) и порядок изменений в нескольких модулях — ровно критерий полного цикла.
- **IV — PASS.** FR-005 опирается на свежий повтор шлюза по `delivered.md` 21 прогона, совпавший с отчётами до символа
  (research R4); гипотеза о причине записана как вывод, с тестом-подтверждением.
- **V — PASS.** Артефакты, события, срок хранения и команды названы в contracts/ и quickstart.md; пакет WP-9 обновляет
  `docs/LOGGING_AND_ARTIFACT_RETENTION.md`.
- **VI — PASS.** Каждый пакет владеет перечнем файлов; рефакторинг вне перечня запрещён.
- **VII — PASS с обязательствами.** Предикаты отката, отбор абзацев второго прохода, поэлементный учёт примечаний — по
  форме (цифры, письмо букв, префикс, маркеры, длина, форма цепочки примечаний 067). Словаря числительных нет (число
  словами — консервативный откат). Правила, которые ВЫЧИТАЮТ из счёта дефектов (поэлементный учёт шлюза FR-005),
  несут анти-вакуумный тест (настоящий непереведённый комментарий продолжает считаться — WP-5).
- **VIII — PASS.** Все утверждения о коде сверены 2026-11-09 на `64f8856`; данные bake-off датированы, их пределы записаны
  (research R1–R4: «данные C не доказывают ≤ 10 %», «по отдельным ответам Haiku данных нет»).

### После дизайна

PASS. Отклонения от спеки (ниже) — сужения и уточнения в сторону консервативности, каждое с данными; О-4 требует
подтверждения владельца до WP-5. Нарушений, требующих Complexity Tracking, нет.

## Project Structure

### Документация (эта спека)

```text
specs/069-translation-modes/
├── spec.md
├── plan.md                 # этот файл
├── research.md             # замеры R1–R5 с путями скриптов
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── translation-modes-config.md
│   ├── reasoning-api-matrix.md
│   ├── literary-polish-rollbacks.schema.json
│   ├── cost-estimate.md
│   ├── cost-estimate-snapshot.schema.json
│   └── events.md
└── tasks.md                # следующий шаг (/speckit-tasks), не этот
```

### Исходный код (затронуто / создано)

```text
src/docxaicorrector/
├── core/
│   ├── translation_modes.py            # НОВЫЙ  WP-1: контракт [translation_modes.*], резолвер, единое разрешение
│   ├── config.py                       # WP-1: поля AppConfig translation_mode_default / translation_modes
│   ├── config_loader_layers.py         # WP-1: сборка payload (если раздел читается здесь)
│   └── model_accounting.py             # WP-3: reasoning/cache-поля, стадия literary_polish, pass_counter_scope
├── generation/
│   ├── _generation.py                  # WP-2: GenerationRequestProfile, reasoning по API, множитель лимита, лестница
│   └── output_budget.py                # НОВЫЙ  WP-2: таблица множителей модели с происхождением
├── image/shared.py                     # WP-2: drop_rejected_optional_param — вложенный extra_body.reasoning
├── text/
│   ├── glossary_pass.py                # WP-2: glossary_max_output_tokens(entry_count, *, multiplier)
│   └── polish_checks.py                # НОВЫЙ  WP-4: предикаты отката P1–P6, P2′ (чистые функции)
├── pipeline/
│   ├── literary_polish.py              # НОВЫЙ  WP-6: отбор, вызов, откат, сборка, артефакт, события
│   ├── block_execution.py              # WP-5 (аппарат FR-005), затем WP-6 (крюк, кеш промпта, профиль 1-го прохода)
│   ├── contracts.py                    # WP-6: state.polish_system_prompt; initialization.polish_client/_model_id; протокол MarkdownGenerator (+request_profile)
│   ├── setup.py                        # WP-6: клиент модели второго прохода
│   ├── glossary_phase.py               # WP-6: профиль первого прохода для вызовов глоссария
│   ├── output_validation.py            # WP-5: части цепочки примечаний (непереведённая часть, записи-комментарии)
│   ├── quality_gate.py                 # WP-5: поэлементный учёт untranslated_body для цепочек примечаний
│   ├── cost_estimate.py                # НОВЫЙ  WP-7: оценка текстовых стадий (без сети, без Streamlit)
│   ├── price_list.py                   # НОВЫЙ  WP-7: прайс OpenRouter + датированный кеш
│   └── _pipeline.py                    # WP-8: событие cost_estimate_vs_actual рядом с model_usage_accounted
├── processing/processing_runtime.py    # WP-8: build_result_bundle(cost_estimate_snapshot=…, cost_actual=…)
├── runtime/artifact_retention.py       # WP-6: LITERARY_POLISH_ROLLBACKS_MAX_AGE_SECONDS / _MAX_COUNT
├── ui/
│   ├── _ui.py                          # WP-8: st.radio режима, скрытие модели/интенсивности для translate, цена
│   ├── _app.py                         # WP-8: единое разрешение, оценка в сессии, снимок при «Старт», факт рядом
│   └── locales/ru.json, en.json        # WP-8
├── validation/profiles.py              # WP-1: RunProfile.translation_mode, разрешение через core/translation_modes
└── resources/
    ├── config.toml                     # WP-1: [translation_modes.standard|quality], translation_mode_default
    ├── cost_estimate_coefficients.json # НОВЫЙ  WP-7: таблица v1 (замораживается до FR-008)
    └── prompts/
        ├── operation_literary_polish.txt   # WP-6: числа как в тексте, маркеры пунктов, не переводить чужое письмо
        └── operation_translate.txt         # WP-5: правило 12 — решать по каждому примечанию (см. О-4)
corpus_registry.toml                    # WP-1: translation_mode = "single" у 17 translate-профилей + 2 новых профиля
tests/artifacts/real_document_pipeline/run_lietaer_validation.py   # WP-9
docs/LOGGING_AND_ARTIFACT_RETENTION.md  # WP-9
```

**Structure Decision**: одно приложение; новые модули кладутся рядом с соседями по слою (`core/` — контракт конфига,
`generation/` — бюджет вызова, `text/` — чистые проверки текста, `pipeline/` — исполнение и оценка). Чистые модули
(`polish_checks`, `cost_estimate`, `output_budget`, `translation_modes`) не импортируют Streamlit и сеть — это и делает
их пакеты параллельными.

---

## Дизайн по требованиям

### FR-001 — контракт режимов и ОДНО разрешение

**Решение.** Новый модуль `core/translation_modes.py`:

- `load_translation_modes(config_data) -> TranslationModesConfig` — читает `translation_mode_default` и
  `[translation_modes.standard]`, `[translation_modes.quality]` (схема — `contracts/translation-modes-config.md`), затем
  переменные окружения `DOCX_AI_TRANSLATION_MODE_DEFAULT`, `DOCX_AI_TRANSLATION_MODES_<MODE>_<FIELD>` (правило 066:
  TOML, затем окружение; читается через `ReadTrackingConfigData`, неизвестный ключ раздела даёт `config_key_ignored`
  автоматически, `core/config_loader_layers.py:8-35`). Валидация: модель — через `resolve_model_selector(...,
  "responses_text")`; интенсивность — из `_PROMPT_EDITORIAL_INTENSITY_PATHS`; рассуждение — `low | medium | high |
  minimal` или пусто; неизвестный режим — ошибка загрузки конфига (не молчаливый откат).
- `resolve_effective_translation_config(app_config, *, processing_operation, requested_mode, requested_model,
  requested_intensity, origin) -> EffectiveTranslationConfig | None` — **единственная** функция, которую зовут UI
  (`ui/_app.py`) и раннер (`validation/profiles.py::resolve_runtime_resolution`). Для `edit`/`audiobook` → `None`
  (ничего не трогает). Для `translate`: режим `requested_mode or translation_mode_default`; `single` — модель
  `requested_model or [models.text].default`, интенсивность `requested_intensity or editorial_intensity_default`,
  рассуждения нет, второго прохода нет (сегодняшнее поведение); `standard`/`quality` — значения режима ПОБЕЖДАЮТ, а
  если `requested_model`/`requested_intensity` заданы явно и отличаются — WARNING `translation_mode_overrides_setting`
  с именами полей и `origin` (`ui` / `run_profile:<id>`).
- `apply_effective_translation_config(app_config_dict, effective) -> dict` — пишет `model` (первый проход),
  `editorial_intensity_default`, `translation_mode`, `translation_first_pass_reasoning_effort`,
  `translation_polish_model`, `translation_polish_reasoning_effort` (ключи — `data-model.md`); их читают конвейер и
  отчёт. `ResolvedRuntimeConfig` получает те же поля → `runtime_overrides` и runtime-config отчёта.

**Run-профиль.** `RunProfile.translation_mode: str | None` (`_optional_choice` из `standard|quality|single`). Профиль
без поля → `translation_mode_default` (как UI). Все 17 существующих translate-профилей `corpus_registry.toml`
(строки 154, 187, 198, 210, 233, 251, 269, 287, 305, 322, 335, 346, 366, 388, 411, 427, 461 на `64f8856`) получают
`translation_mode = "single"` — их история (шестой/пятый прогоны, бенчмарки структуры, сравнения reader cleanup)
сопоставима только с одним проходом. Для FR-008 — два новых профиля-копии
`ui-parity-translate-benchmark-advisory-image-safe-no-cleanup`: `ui-parity-translate-benchmark-standard` и
`ui-parity-translate-benchmark-quality`. Гард-тест: каждый translate-профиль реестра объявляет `translation_mode`
явно (иначе правка дефолта молча удвоит цену чьего-то регрессионного прогона).

**Альтернативы.** (а) Разрешать режим отдельно в UI и в раннере — именно так расходятся `ui/_ui.py:615` и
`validation/profiles.py:250` сегодня (находка 8 Codex). (б) Режим как «ещё один профиль модели» в `[models.text]` —
не выражает второй проход и рассуждение.

### FR-002 — UI

**Решение.** `render_sidebar` (`ui/_ui.py:595`): для `translate` рисуется `st.sidebar.radio` с ключом
`sidebar_translation_mode`, варианты `standard`/`quality`, `format_func` — подпись из `ui/locales` плюс цена из
сессии («Стандарт · ≈ 0,90–1,05 $»); без оценки — без цены и `st.sidebar.caption` «цена появится после загрузки
документа»; без прайса — «цена неизвестна». Для `translate` селектор модели в «Дополнительно» не рисуется, виджет
интенсивности уже рисуется только для `edit` (`:616`); предупреждение о доступности модели проверяет обе
эффективные модели режима. Кортеж `render_sidebar` растёт до 13 элементов (`translation_mode` последним);
`_resolve_sidebar_settings` (`ui/_app.py:307-322`) дополняет старые формы пустым режимом.

`ui/_app.py::main` (`:821-845`) после сайдбара зовёт `resolve_effective_translation_config(...)` с `requested_model=None`
и `requested_intensity=None` для `translate` (виджетов нет — значит и запрошенного нет) и `apply_…` к `app_config`.
Оценка: когда для текущего файла и `translate` есть подготовленный контекст, `_app` считает
`estimate_text_stages(...)` для обоих режимов (WP-7) и кладёт в сессию под ключом `(file_token, prepared_source_key,
source/target, coefficients_version, price_list_date)`; сайдбар следующего прохода читает её. Это даёт одну задержку
перерисовки после подготовки — допустимо («до загрузки — без цены»).

Переходы операций и рекомендации (`ui/recommended_text_settings.py`) режим не трогают: рекомендация меняет только
операцию и языки; тесты WP-8 проходят edit → translate → edit и применение рекомендации и проверяют, что интенсивность
`edit` и модель `edit` прежние, а режим перевода не утекает в `edit`.

**Альтернативы.** Радио в основной области у кнопки «Старт» — цена видна сразу после подготовки без лишней перерисовки,
но спека и прежняя раскладка держат настройки в сайдбаре; оставлено как запасной вариант, если задержка окажется
заметной на AppTest.

### FR-003 — рассуждение: матрица API и учёт

**Решение.** `generation/_generation.py` получает `GenerationRequestProfile` (frozen dataclass: `reasoning_effort:
str | None`, `output_budget_multiplier: float`, `usage_stage: str`) и ключевой аргумент `request_profile: … | None =
None` у `generate_markdown_block` и `request_text_completion`. `None` → профиль по умолчанию, запрос побайтно прежний.
Внутри файла профиль протаскивается в `_build_request_kwargs` (`:2243`), `_recover_from_persistent_empty_response`
(`:2357`), `_attempt_degradation_ladder` → `_ladder_translate_unit` → `_ladder_model_answer` (`:2911`, вложенный
`generate_markdown_block`) и в `_call_markdown_request_with_sdk_fallback` (стадия учёта сейчас там жёстко
`text_generation`, `:2295`).

Матрица (`contracts/reasoning-api-matrix.md`):
- **Responses** — `request_kwargs["reasoning"] = {"effort": e}`; `_call_responses_create` (`:1934`) добавляет
  `"reasoning"` в `retryable_optional_params`; отказ провайдера вида `Unsupported parameter: 'reasoning'` снимается
  `drop_rejected_optional_param` с WARNING `model_call_param_dropped` (`image/shared.py:113`), прогон не падает.
- **OpenRouter Chat Completions** (`_call_chat_completions_create`, `:2043`) — `payload["extra_body"] = {"reasoning":
  {"effort": e}}`; `drop_rejected_optional_param` учится снимать вложенный ключ: если названный параметр не на верхнем
  уровне, ищет его в `payload["extra_body"]` и удаляет там (`removable_params` получает `"reasoning"`).
- **Нативный Anthropic** (`:2173`) — параметр не передаётся; WARNING `reasoning_effort_not_supported_for_provider` один
  раз на пару (модель, уровень) в процессе (множество в `_generation.py`; учёт WP-3 здесь не нужен, пакеты не пересекаются).
- Сервисные вызовы проверки границ и картинок профиль не получают (они идут не через эти функции).

Учёт (`core/model_accounting.py`): `ModelCallUsage` получает `reasoning_tokens: int | None` (Responses —
`usage.output_tokens_details.reasoning_tokens`, Chat — `usage.completion_tokens_details.reasoning_tokens`; поля нет →
`None`), `cached_tokens: int | None` (`input_tokens_details.cached_tokens` / `prompt_tokens_details.cached_tokens`),
`cache_write_tokens: int | None`, `cache_discount_usd: float | None` (как OpenRouter их отдаёт, без вычислений);
`_StageTotals` — суммы и счётчики «поле отсутствовало» (`reasoning_unreported_call_count`), то есть «неизвестно ≠ 0».
Отчёт и `run_summary` показывают их по стадиям (WP-9).

**Альтернативы.** Ставить `reasoning` в единой точке `call_responses_create_with_retry` — не покрывает Chat и Anthropic,
которые собирают запрос заново (`:2055-2058`), и задевает картинки и проверку границ (находка 6 Codex).

### FR-004 — второй проход «литературная шлифовка»

**Место.** `pipeline/block_execution.py::process_single_block` — после `processed_block_status ==
"valid"` (`:2278-2282`) и до `model_kept_apparatus` (`:2286`); новый инжектируемый `literary_polish_fn` (по образцу
остальных `*_fn` этой функции). Шлифовка не идёт, если: режим без второго прохода; блок — сквозной, оставлен политикой
(`policy_kept_chunk`), маршрутизирован как оглавление (`toc_dominant`); статус блока не `valid`. Всё, что после крюка
(аппарат, восстановление сносок `:2349`, реестр `:2370`, проекция аудиокниги `:2358`, учёт задней части `:2393`), видит
итоговый текст.

**Что шлифуется** (`pipeline/literary_polish.py`, `select_polish_paragraphs`): абзацы со статусом первого прохода
`accepted` (`marker_paragraph_dispositions`) И долей букв целевого письма ≥ 0,5 в тексте первого прохода (О-1).
Блок без записи по абзацам шлифуется, только если в нём ровно один абзац (`payload.paragraph_ids` длины 1) — с одним
маркером; многоабзацный блок без маркеров (маркеры выключены) не шлифуется — счётчик `skipped_unmarked_block_count`.

**Вызов.** `dependencies.generate_markdown_block(client=initialization.polish_client, model=initialization.polish_model_id,
system_prompt=<кеш literary_polish>, target_text=<отобранные абзацы с маркерами [[DOCX_PARA_id]]>, context_before=<хвост
доставленного текста предыдущего блока, той же длины, что payload.context_before>, context_after="", max_retries=
context.max_retries, expected_paragraph_ids=<отобранные id>, marker_mode=True, block_index=index,
allow_controlled_source_fallback=False, should_stop=…, request_profile=<профиль второго прохода: reasoning модели
шлифовки, её множитель, стадия literary_polish>)` внутри `model_accounting.pass_counter_scope("literary_polish")`.
`allow_controlled_source_fallback=False` — «ответь или подними»: ни лестницы, ни подстановки источника; любая ошибка
поднимается и превращается в откат к первому проходу. Промпт: `load_system_prompt(operation="translate",
prompt_variant="literary_polish", …)` с теми же аргументами, что первый проход (`pipeline/support.py::build_system_prompt_arguments`
— операция `translate`, значит контекст документа и глоссарий прогона в нём есть, `support.py:21`), кешируется в новом
поле `state.polish_system_prompt` (`_get_cached_system_prompt` получает ветку `literary_polish`, `:1146`).
`operation_literary_polish.txt` получает три правила: числа записывать так же, как в тексте (цифры — цифрами, слова —
словами); маркеры и номера пунктов не менять; фрагменты на другом письме (имена, названия, ссылки) не переводить и не
транслитерировать.

**Проверка и откат** (`text/polish_checks.py`, research R1): по абзацу против первого прохода — P1 числа, P2 новое слово
не целевого письма, P2′ исчезнувшее слово не целевого письма (О-2), P3 смешанный алфавит, P4 префикс пункта после
нормализации маркеров, P5 потерянная сноска, P6 длина вне [0,70; 1,50]. Любое срабатывание — абзац получает текст
первого прохода; ответ со статусом не `accepted` (`omitted`/`source_restored` — генератор подставил в них текст первого
прохода) — тоже откат с причиной `not_accepted`. Если ответ не вернул ровно отобранные id в том же порядке — откат
блока (`block_marker_mismatch`). Статусы абзацев НЕ меняются: итоговая запись блока — `MarkerPreservedBlockText` с
теми же `ParagraphDisposition.status`, текстом шлифовки там, где она принята.

**Отказ и Stop.** Исключение второго прохода (`Exception`) → первый проход, WARNING `literary_polish_block_failed`
(причина, класс ошибки, блок). `LatePhaseStopped` наследует `BaseException` (`_generation.py:2636-2641`) и сегодня
означает «блок не доставлен, прогон остановлен» (`block_execution.py:2454-2458`). Для второго прохода спека требует
иного: первый проход блока остаётся. Поэтому `literary_polish` ловит `LatePhaseStopped` явно, возвращает первый проход
с WARNING (причина `stopped`) и ставит `state.stopped_during_polish = True`; `run_block_processing_phase` проверяет
флаг сразу после `process_single_block` и возвращает `_emit_stopped(index + 1)` — в том числе на последнем блоке, где
обычной проверки между блоками уже не будет. Прогон завершается как остановленный, как сейчас.

**Учёт один раз.** Счётчики disposition первого прохода записаны его терминальным возвратом
(`_deliver_marker_preserved_block`, `_generation.py:334-354`); шлифовка статусы не меняет, поэтому итоговые счётчики
= счётчики первого прохода. Всё, что генератор пишет внутри шлифовки (disposition, повторы, путь API, удаления текста),
`pass_counter_scope` направляет в раздел `literary_polish` снимка, а не в общие счётчики. Свои счётчики второго
прохода: `sent_paragraph_count`, `accepted_paragraph_count`, `rolled_back_paragraph_count`,
`rollback_reason_counts`, `block_rollback_count`, `failed_block_count`, `skipped_paragraph_counts` (по причинам),
`artifact_path`. Стадия бухгалтерии — `literary_polish`.

**Артефакт откатов** (`contracts/literary-polish-rollbacks.schema.json`): строка JSONL на каждый откат абзаца или блока в
`.run/literary_polish_rollbacks/<run_id>.jsonl` (`RUN_DIR`; раннер изолирует `.run` прогона через `DOCX_AI_RUN_DIR`),
срок и число — как `marker_attempts` (7 дней, 400 файлов), чистка `prune_artifact_dir` после записи; событие
`literary_polish_paragraph_rolled_back` (WARNING, без текстов — тексты только в артефакте, §1.5 документа логирования).
Раннер копирует файл в `runs/<run_id>/literary_polish_rollbacks.jsonl` и пишет счётчики + путь в отчёт (WP-9).

**Альтернативы.** (а) Шлифовать внутри `generate_markdown_block` — генератор не знает политики аппарата и статуса блока.
(б) После реестра — реестр, сноски и аудиокнига получили бы первый проход. (в) Шлифовать отдельной фазой после всех
блоков — нужен повторный проход по реестру и сборке, а импорт DOCX спека запрещает. (г) Повторять второй проход
лестницей — лишняя цена ради абзаца, у которого уже есть хороший первый проход.

### FR-005 — примечания в конце главы

Механизм (research R4): правило аппарата адресовано абзацу, а абзац-цепочка смешивает ссылки и комментарии; шлюз
считает такой абзац целиком, и ветка URL (`quality_gate_text_detectors.py:76-78`) делает длинную запись с URL
«не библиографией». Правка по форме — WP-5:
- **шлюз** (`pipeline/quality_gate.py`, сбор образцов `:560-603`): если доставленный текст — цепочка примечаний
  (`output_validation.notes_run_parts`), образец строится из его непереведённой части (`notes_run_untranslated_part`:
  ведущий текст и записи с долей латиницы ≥ 0,8, не являющиеся ссылкой по per-entry-тесту 067); пороги образца
  (280 символов, 30 слов) и документа (2 000 символов, 2 %) прежние; `char_count` образца — длина непереведённой части.
  Для всех прочих абзацев путь не меняется;
- **запрос** (`_build_block_apparatus_prompt`, `block_execution.py:708-746`): для абзацев-цепочек в маркерном режиме
  добавляется строка «В абзаце [[DOCX_PARA_id]] авторский текст есть в примечаниях N, M: его переведите, ссылки и имена
  авторов в них оставьте» (номера — `notes_run_commentary_numbers`, та же per-entry форма); правило 12
  `operation_translate.txt` получает фразу «решайте по каждому примечанию, а не по абзацу целиком; имя автора — часть
  ссылки».

Отрицательные тесты: (1) цепочка с непереведённой записью-комментарием ≥ 280 символов продолжает давать образец и
блокировать документ выше порогов (повтор D: 6 689 → 3 656, всё ещё выше); (2) обычный абзац с URL и 40+ словами
латиницей считается как раньше; (3) абзац из одних ссылок не получает строки «авторский текст есть в примечаниях».

### FR-006 — бюджеты вывода

`generation/output_budget.py`: `MODEL_OUTPUT_BUDGET_MULTIPLIERS` — модель (канонический id без провайдера) → множитель
с комментарием происхождения; неизвестная модель → 1,0. v1: `google/gemini-3.1-flash-lite-preview` 1,0;
`google/gemini-3.7-flash` 1,0 (low: p99 = 0,289 лимита, 0 обрывов из 56); `google/gemini-3.8-flash` 1,0 (low: p99
0,277, n = 28); `anthropic/claude-haiku-5.5` 3,0 (предварительно, research R2; уточняет WP-0). Профиль запроса несёт
множитель модели своего прохода.

`_estimate_max_output_tokens(target_text, multiplier=1.0)`: `base = max((len // 3) * 4, 512)`; `limit = base` при
m = 1, иначе `ceil(base * m)`; `min(limit, _MODEL_OUTPUT_TOKEN_CEILING)`. Лестница: `_LADDER_BUDGETABLE_SOURCE_CHARS`
становится функцией `_ladder_budgetable_source_chars(m) = CEILING * 3 // (4 * m)` (m = 1 → 12 288 — прежняя
константа). `_boost_request_output_budget` не меняется (удвоение от текущего лимита, потолок прежний). Глоссарий:
`glossary_max_output_tokens(entry_count, *, multiplier=1.0)` — множитель применяется ко всей формуле, включая минимум
1 024, затем потолок; вызов передаёт множитель модели первого прохода.

### FR-007 — оценка цены

`pipeline/cost_estimate.py` — чистый модуль: вход `EstimateInput` (число LLM-заданий, абзацев, символов источника по
подготовленному документу; пара языков; проходы режима: модель, стадия), `CoefficientTable` (из
`resources/cost_estimate_coefficients.json`), `PriceList | None`; выход `CostEstimate` (по стадиям `glossary_extraction`,
`text_generation`, `literary_polish`: токены ввода/вывода, верх по прайсу, низ по сценарию скидки модели, подпись «без
картинок»). Формулы — `contracts/cost-estimate.md`: якорь — форма документа для модели первого прохода `single`, прочие
модели/стадии — отношение к якорю на тех же главах (research R3). Пара языков, которой нет в таблице, → оценка с флагом
`coefficients_extrapolated` и подписью «приблизительно» (не молчаливое использование en→ru).

`pipeline/price_list.py`: `get_price_list(now) -> PriceList | None` — кеш `.run/price_list/openrouter_models.json`
(`fetched_at`, цены вход/выход на модель), свежий (< 24 ч) — без сети; иначе запрос `https://openrouter.ai/api/v1/models`
с тайм-аутом 5 с; ошибка → последний кеш с его датой и WARNING `price_list_fetch_failed`; нет кеша → `None` → UI «цена
неизвестна». Нативные `anthropic:`/`openai:` модели в прайсе OpenRouter не ищутся → «цена неизвестна» для их стадий.

`model_accounting` не получает ни одной оценочной цифры: оценка живёт в `app_config["cost_estimate_snapshot"]` прогона,
в bundle и в событии `cost_estimate_vs_actual` (`pipeline/_pipeline.py`, рядом с `emit_run_model_accounting_event`
`:1167`), которое берёт ФАКТ из снимка учёта по тем же стадиям: `cost_usd_reported_by_provider` стадий
`glossary_extraction` + `text_generation` + `literary_polish`, `relative_error_vs_upper = (факт − верх) / факт`,
`within_range`. Частичный или остановленный прогон помечается `run_complete: false` — его ошибку не сравнивают.

Снимок (`contracts/cost-estimate-snapshot.schema.json`) замораживается при нажатии «Старт» из оценки выбранного режима;
`build_result_bundle(..., cost_estimate_snapshot=None, cost_actual=None)` (`processing_runtime.py:1684`) кладёт оба;
экран результата показывает факт рядом со СВОЕЙ оценкой; bundle без снимка — без оценки. Раннер считает ту же оценку
до прогона и кладёт её в отчёт (`cost_estimate` + `cost_estimate_vs_actual`).

### FR-008 — платный замер

Не код. После слияния WP-1…WP-9, зелёного полного прогона в главном дереве и приёмочного ревью Codex: коэффициенты
v1 заморожены (версия в отчёте), владелец подтверждает сумму (≈ 5–6 $: «Стандарт» ≈ 0,9–1,2 $ и «Качество» ≈ 1,8–1,9 $
на книгу, research R3), прогоны — `scripts/run-real-document-validation.sh` с профилями
`ui-parity-translate-benchmark-standard` / `-quality` для `lietaer-pdf-full-benchmark` и
`money-sustainability-pdf-full-heldout`. Слепое чтение — по SC-001/SC-002 (quickstart.md, сценарий 6).

---

## Отклонения от спеки

Каждое — сужение или уточнение; ни одно не ослабляет проверку. Все приняты оркестратором 2026-11-09 (технические
развилки; спека, Changelog «Решения оркестратора по отклонениям плана») — О-4 внесён в SC-006 и Anti-regression 1.

- **О-1. Отбор абзацев второго прохода сужен (FR-004 (1)).** Спека: «только абзацы со статусом `accepted`». План:
  `accepted` **и** доля букв целевого письма в тексте первого прохода ≥ 0,5. Основание: ссылки, оставленные по D1, имеют
  статус `accepted` (модель вернула их сама; Money A p0102–p0111 — доля латиницы 0,61–0,99 у p0102–p0104, p0107,
  `fr005_notes_mark.out`); шлифовка ru→ru, получив английскую ссылку, может её перевести, и ни один предикат этого не
  видит. Отказ от шлифовки таких абзацев — консервативен и дешевле.
- **О-2. Добавлен предикат P2′ «исчезло слово не целевого письма, бывшее в первом проходе» (FR-004 (4)).** На C — 0
  срабатываний из 206 (`polish_lost_latin.out`). Защищает D1 в смешанных абзацах, которые О-1 пропускает (доля целевого
  письма ≥ 0,5, но внутри — ссылки латиницей).
- **О-3. P4 сравнивает префикс после нормализации маркеров доставки.** Уточнение формулировки «изменился префикс
  нумерации пункта»: без него 3 из 10 откатов на C ложные («•» → «-», доставка делает это сама; research R1).
- **О-4. FR-005 меняет запрос и для `single`** (раздел аппарата блока и правило 12 — общие для перевода). SC-006 и
  Anti-regression 1 («`single` — тот же промпт») в буквальном прочтении это запрещают; разводить FR-005 по режимам —
  значит держать два варианта D1. Предложение: SC-006 читать как «тот же запрос, кроме правки FR-005 в блоках с
  цепочками примечаний»; тест WP-2 фиксирует байты запроса `single` на блоке без цепочки примечаний. **Требует решения
  владельца.**
- **О-5. Замер FR-006 «вызов глоссария Haiku на Money гл. III возвращает полный список» недостижим в режимах.**
  Глоссарий строит модель первого прохода (`pipeline/glossary_phase.py:346`): во «Стандарте» это flash-lite, Haiku только
  шлифует. Замер потребовал бы отклонённой конфигурации D. Замена: юнит-тест бюджета (множитель 3 → 16 384 и 3 072 для
  `optional`/`required`, research R2) и, если владелец захочет, WP-0.
- **О-6 (уточнение). Сценарий скидки — только для стадий модели, у которой скидка наблюдалась** (flash-lite; Haiku и
  gemini-3.7 на главах — 1,000). Спека говорит «для других моделей не проверено» — план это исполняет буквально: их
  нижняя граница = верхней, подпись «скидка не наблюдалась». Следствие: вилка «Качества» ≈ 1,8–1,9 $, а не 1,4–1,9 $
  из D-1.
- **О-7 (уточнение). Контекст второго прохода** — до: хвост доставленного (целевого) текста предыдущего блока; после:
  пусто. В bake-off C контекст был русским с обеих сторон (харнес над DOCX первого прохода); английский контекст
  источника для шлифовки ru→ru не дан намеренно.
- **О-8 (уточнение). Таблица коэффициентов — по форме документа, якорь — полные книги, а не главы.** Таблица «на символ»
  из глав недооценивает книги на 31–35 % (research R3); спека требует «(модель, стадия, языковая пара) с
  происхождением» — ключ сохранён, формула учитывает вызовы и абзацы.

Ошибок фактов в спеке не найдено; одно уточнение к «Что измерено»: «Haiku считает тот же русский текст ≈ 3× токенов»
(costs.md) — вывод из агрегатов; обрывные ответы Haiku несут элемент `reasoning` (research R2), часть расхода может быть
рассуждением. На решения D-1 это не влияет.

---

## Порядок реализации: пакеты работ

Каждый пакет — отдельная ветка в отдельном боковом worktree вне репозитория (`D:\Temp\claude\wt-069-<N>`, `.venv` —
симлинком; AGENTS.md «Боковые worktree»). Тесты истории (`test_spec_status_consistency`) — только в главном дереве.
Каждый пакет начинает с характеристических тестов того, что должно остаться прежним, и только потом меняет код.

### Волна 1 — параллельно, файлы не пересекаются

| Пакет | Владеет файлами | Доказывающие тесты (анти-вакуум: падает без изменения) |
|---|---|---|
| **WP-0** (не код; платно ≈ 0,06–0,12 $, по согласию владельца; можно пропустить) | — (данные в `D:\Temp\docxai-research\069-wp0\`) | Отладочный харнес шлифовки (`polish_runner.py` + запись `responses.create` как в `reasoning_runner.py`) на двух главах bake-off, Haiku без параметра и с `effort=low`: по каждому ответу вывод, рассуждение, статус, лимит. Итог — множитель Haiku и ответ, рассуждает ли Haiku. |
| **WP-1** Конфиг и разрешение (FR-001 ядро) | `core/translation_modes.py` (нов.), `core/config.py`, `core/config_loader_layers.py`, `resources/config.toml`, `validation/profiles.py`, `corpus_registry.toml`, `tests/test_translation_modes.py` (нов.), `tests/test_config.py`, `tests/test_real_document_validation_corpus.py` (профили и реестр) | контракт TOML+env (env побеждает TOML); неизвестный ключ `[translation_modes.quality]` → `config_key_ignored`; `standard`/`quality` побеждают `model` и интенсивность с WARNING и именами полей (падает без резолвера); профиль без поля → `translation_mode_default`; `single` = прежние модель/интенсивность, без рассуждения; `edit`/`audiobook` → `app_config` побайтно прежний; гард «каждый translate-профиль объявляет режим» (падает на текущем реестре) |
| **WP-2** Профиль запроса, матрица рассуждения, бюджеты (FR-003 генератор, FR-006) | `generation/_generation.py`, `generation/output_budget.py` (нов.), `image/shared.py`, `text/glossary_pass.py`, `tests/test_generation_request_profile.py` (нов.), `tests/test_output_budget.py` (нов.), `tests/test_glossary_pass.py` | СНАЧАЛА золотой тест SC-006: `_build_request_kwargs`, запрос восстановления и лестницы для `edit`/`audiobook`/`translate` без профиля — байты как до правки; затем: Responses несёт `reasoning` при профиле и не несёт без; Chat несёт `extra_body.reasoning`; синтетический отказ `Unsupported parameter: 'reasoning'` снимает вложенный ключ и пишет WARNING (Responses и Chat); Anthropic — параметра нет, WARNING один раз; лестница и восстановление несут профиль (падает, если протаскивание забыто); лимиты m = 1 на длинах 0/383/384/6 000/12 288/20 000 равны прежним, m = 3 — ожидаемым; `_ladder_budgetable_source_chars(1) == 12288`; глоссарий m = 1 равен прежнему, m = 3 → 3 072 и 16 384 |
| **WP-3** Учёт (FR-003 учёт, FR-004 (6), поля кеша FR-007) | `core/model_accounting.py`, `tests/test_model_accounting_069.py` (нов.; отдельного файла тестов учёта сейчас нет) | `reasoning_tokens` из Responses и Chat; ответ без поля → `None` и `reasoning_unreported_call_count += 1` (падает, если записать 0); поля кеша читаются и суммируются, отсутствие → неизвестно; стадия `literary_polish` в `stages`; `pass_counter_scope("literary_polish")`: disposition/повторы/путь API/удаления текста внутри области не меняют общие счётчики (падает без области); вложенность областей и выход по исключению |
| **WP-4** Предикаты отката (FR-004 (4)) | `text/polish_checks.py` (нов.), `tests/test_polish_checks.py` (нов.) | на вымышленных парах той же формы, что 7 срабатываний C (без текста книг, Конституция VII / гард 066): каждый предикат ловит свою форму и молчит на хорошей правке; «23 → 32», «1.5 → 15», «23 → двадцать три» ловятся P1; «•» → «-» не ловится P4, «2.» → «1.» ловится; длина 0,69 и 1,51 ловится, 0,82 и 1,43 нет; P2/P2′ для целевого латинского письма (en) работает симметрично; URL и e-mail токены игнорируются |
| **WP-5** Примечания (FR-005; после решения О-4) | `pipeline/quality_gate.py`, `pipeline/output_validation.py`, `pipeline/block_execution.py` (только `_build_block_apparatus_prompt` и его константы), `resources/prompts/operation_translate.txt`, `tests/test_spec_069_notes_gate.py` и `tests/test_spec_069_notes_apparatus.py` (нов., рядом с `test_gate_detectors_stage2.py` и `test_spec_067_apparatus_in_body.py`) | цепочка «ссылки + один английский комментарий ≥ 280 символов» даёт образец длиной комментария (падает без правки: сейчас — вся длина или 0); цепочка только из ссылок с URL и 60+ словами — образца нет (падает без правки — сейчас есть); анти-вакуум: цепочка с английскими определениями (форма D) — образец остаётся, документ блокируется; обычный абзац с URL — как раньше; раздел аппарата называет записи-комментарии и не называет ничего у абзаца из одних ссылок; тест на исходном тексте формы p0102–p0111 (вымышленном), что отметка 067 ставится и раздел уходит в запрос |
| **WP-7** Оценщик и прайс (FR-007 ядро) | `pipeline/cost_estimate.py` (нов.), `pipeline/price_list.py` (нов.), `resources/cost_estimate_coefficients.json` (нов.), `tests/test_cost_estimate.py`, `tests/test_price_list.py` (нов.) | таблица v1 воспроизводит книги research R3 (RM/Money «Стандарт» 1,22/1,05, «Качество» 1,88/1,81 при прайсе 2026-11-09) — регрессия формул; низ = верх для моделей без наблюдённой скидки; без прайса → «цена неизвестна», не ноль; кеш свежий — сети нет (мок сети падает при вызове); сеть упала → старый кеш с датой + WARNING; нет кеша → `None`; модуль не импортирует Streamlit и `model_accounting` (гард импорта) |

### Волна 2 — после слияния зависимостей

| Пакет | Зависит от | Владеет файлами | Доказывающие тесты |
|---|---|---|---|
| **WP-6** Второй проход в конвейере (FR-004) | WP-1, WP-2, WP-3, WP-4; WP-5 слит раньше (общий `block_execution.py`) | `pipeline/literary_polish.py` (нов.), `pipeline/block_execution.py` (крюк, кеш промпта, профиль первого прохода в `_generate_block_chunk`), `pipeline/contracts.py`, `pipeline/setup.py`, `pipeline/glossary_phase.py`, `resources/prompts/operation_literary_polish.txt`, `runtime/artifact_retention.py`, `tests/test_literary_polish.py` (нов.), `tests/test_document_pipeline.py`, тесты `glossary_phase` | через ОБЫЧНЫЙ вход блока с двойником генератора: принятая шлифовка доставлена, реестр/аудиопроекция/сноски видят её (падает без крюка); `omitted`/`source_restored`/`policy_kept_source` не отправлены и не изменены; абзац с долей целевого письма < 0,5 не отправлен (О-1); каждый предикат → откат абзаца, строка артефакта, событие; несовпадение маркеров → откат блока; исключение → первый проход + WARNING; Stop во время шлифовки → первый проход блока доставлен и прогон остановлен, в том числе на ПОСЛЕДНЕМ блоке (падает без флага `stopped_during_polish`); счётчики disposition первого прохода одинаковы со шлифовкой и без (падает без `pass_counter_scope`); кеш промпта: `literary_polish` и `default` — разные строки, `literary_polish` строится один раз; промпт шлифовки содержит контекст документа и глоссарий прогона; `single` и `edit` не вызывают шлифовку; блок без маркеров с одним абзацем шлифуется; глоссарий и все вызовы первого прохода «Качества» несут `effort=low` |
| **WP-8** UI, bundle, событие сравнения (FR-002, FR-007 UI) | WP-1, WP-3, WP-7 | `ui/_ui.py`, `ui/_app.py`, `ui/locales/ru.json`, `ui/locales/en.json`, `processing/processing_runtime.py`, `pipeline/_pipeline.py`, `tests/test_ui_translation_modes.py` (нов., `AppTest`), `tests/test_processing_runtime.py`, `tests/test_ui_i18n.py` | `AppTest`: для `translate` радио с двумя вариантами, «Стандарт» по умолчанию, селектора модели и интенсивности нет; для `edit` — как раньше; до загрузки — без цены, после подготовки — с ценой, без прайса — «цена неизвестна»; переходы edit → translate → edit и рекомендация не меняют модель/интенсивность `edit`; «Старт» замораживает снимок; результат показывает факт рядом со СВОЕЙ оценкой; старый bundle без снимка — без оценки (падает, если показывать текущую оценку); событие `cost_estimate_vs_actual` с формулой ошибки и `run_complete`; локали ru/en с одинаковыми ключами |

### Волна 3

| Пакет | Зависит от | Владеет файлами | Доказывающие тесты |
|---|---|---|---|
| **WP-9** Раннер, отчёт, документ логирования | WP-1, WP-3, WP-6, WP-7, WP-8 | `tests/artifacts/real_document_pipeline/run_lietaer_validation.py`, `docs/LOGGING_AND_ARTIFACT_RETENTION.md`, `tests/test_real_document_pipeline_validation.py` (форма отчёта раннера) | отчёт несёт режим и эффективные модели/интенсивность/рассуждение обоих проходов в runtime-config; `run_summary` — рассуждение и поля кеша по стадиям, строки `literary_polish_*`, путь артефакта откатов (копия в `runs/<run_id>/`); оценка до прогона + сравнение после; события второго прохода попадают в `events.jsonl` (068 FR-002); документ логирования описывает новые события и семьи `.run/literary_polish_rollbacks/`, `.run/price_list/` (гард `test_logging_*`/`_list_log_events.py` — новые события зарегистрированы) |

### Слияние и приёмка

```text
волна 1:  WP-1 ─┐  WP-2 ─┐  WP-3 ─┐  WP-4 ─┐  WP-5 ─┐  WP-7 ─┐   (любой порядок; WP-0 параллельно, вне репо)
волна 2:  WP-6  ← WP-1, WP-2, WP-3, WP-4, WP-5      WP-8 ← WP-1, WP-3, WP-7
волна 3:  WP-9  ← WP-6, WP-8
приёмка:  полный `scripts/test.sh tests/ -q` в ГЛАВНОМ дереве на интеграционной ветке, `git status --porcelain` пуст
          → расширенное ревью Codex по всем затронутым поверхностям (AGENTS.md) → слияние в main → FR-008 (платно, по согласию)
```

После каждого переноса пакета на свежую интеграционную ветку — повторный полный прогон в главном дереве (AGENTS.md,
2026-08-08: зелень до переноса ничего не значит). Тема коммита пакета называет `spec 069` (он и есть работа по ней);
статус спеки обновляется оркестратором вместе с первым слиянием, чтобы `test_spec_status_consistency` не падал.

---

## Сохраняемые контракты AGENTS.md

- **WSL runtime:** все тесты и диагностические импорты — `wsl.exe -d Debian --cd "D:\Work\Projects\DocxAICorrector" --
  bash scripts/test.sh <selector>`; Windows `python` и `.venv-win` не используются; в боковых worktree — только через
  `wsl.exe -d Debian -- bash -lc '...'` с литеральными путями.
- **Каноническая проверка:** финальное «зелёное» — полный `scripts/test.sh tests/ -q` в главном дереве при пустом
  `git status --porcelain`; debug-путь помечается `debug-only` и не выдаётся за канонический.
- **Real-document evidence:** FR-008 — только `scripts/run-real-document-validation.sh`; при падении профиля — сначала
  отчёт прогона и `failed_checks` с `actual`/`threshold`, потом гипотезы; полный прогон — веха, не цикл настройки.
- **Логирование и артефакты:** новые события и семьи `.run/` регистрируются в `docs/LOGGING_AND_ARTIFACT_RETENTION.md`
  (WP-9), полные тексты — только в артефактах, не в логе; `.run/` и `.env` вне git.
- **Line endings:** все новые файлы — LF; после правок `git diff --check`.

## Что не определено (сказано прямо)

- **Множитель Haiku** — по отдельным ответам данных нет; 3 — проекция из агрегатов (research R2). Уточняет WP-0 или первый
  прогон FR-008 (учёт рассуждения по стадиям WP-3).
- **Рассуждает ли Haiku по умолчанию** через OpenRouter и сколько это стоит — признак есть (элемент `reasoning` в обрывных
  ответах), числа нет. Конфиг «Стандарта» оставляет Haiku без параметра — как в замеренном C; менять — только после замера
  качества.
- **Причина скидки 21–24 %** — полей кеша нет ни в одном сохранённом отчёте; WP-3 начинает их писать, ответ даст FR-008.
- **Доля ложных откатов ≤ 10 % (SC-001)** — на C 0 из 7, но верхняя 95 %-граница ≈ 41 %; доказывается только чтением
  откатов FR-008.
- **Исправит ли правка запроса FR-005 поведение моделей (условия (а)/(б))** — проверяется только прогоном; детерминированно
  проверяется лишь, что запрос несёт нужную строку.
- **Наличие раздела аппарата в запросах bake-off** выведено повтором детектора 067 на сохранённом тексте; текст промпта
  не логируется — подтверждение в тесте WP-5.
- **Ошибка оценки на книгах вне выборки** — «без одной книги» −26…+28 % для якоря (`cost_form_fit_jobs.out`); SC-005 «≤ 25 %» — гипотеза на краю, на одной из двух книг вероятно превышение.

## Complexity Tracking

Нарушений Конституции, требующих обоснования, нет.
