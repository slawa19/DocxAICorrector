# Implementation Plan: P2 спеки 063 — глоссарий прогона (FR-013…FR-016)

**Branch**: `063/glossary-pass` | **Date**: 2026-11-07 | **Spec**: [spec.md](spec.md)

**Input**: `specs/063-translation-fidelity/spec.md` — решение владельца D2 (= «да», 2026-11-07),
FR-013…FR-016, SC-006, находки M-1 и M-4. Только блок P2; P0/P1/P3 этой спеки план не трогает.

Все ссылки на код проверены на `e1f1aed` (2026-11-07), если не сказано иное.

## Summary

Каждый текстовый вызов книги переводит свой блок в одиночку, поэтому авторский термин получает
столько передач, сколько блоков его встретили (M-1: *bank-debt money* — семь, *resilience* и
*sustainability* — одна «устойчивость», *value* — «стоимость» в главах 1–6 и «ценность» в 8–9;
M-4: Montpelier двумя написаниями, Lietaer — «Литер»). Слот для общей памяти есть
(`DocumentContextProfile.glossary_terms`, `src/docxaicorrector/document/segments.py:118`, рендер `:185-196`, потолок `max_glossary_terms=8` — `:151`), но в
домене `general` он пуст: его наполняет только богословский список
(`src/docxaicorrector/processing/preparation.py:519-541`).

План: в начале прогона `translate`, после инициализации и до первого блока, **один** проход:

1. детерминированно, **по форме**, без списков слов, собрать кандидатов из того текста книги,
   который этот прогон отправит модели (регион `prose` + `front_matter`, только `llm`-задания);
2. **один** вызов текстовой модели прогона закрепляет передачи `{source_term, target_term,
   kind: term|name, note}`; ответ принимается только для терминов из списка кандидатов;
3. результат — записи `GlossaryTerm` — рендерится тем же рендерером, что и слот профиля, с
   потолком по **бюджету символов**, а не по числу 8, и дописывается к `document_context_prompt`,
   который уже доходит до системного промпта каждого блока `translate`
   (`src/docxaicorrector/pipeline/block_execution.py:454-467`);
4. артефакт `.run/run_glossaries/*.json`, события `run_glossary_built` / `run_glossary_failed`,
   секция `run_glossary` в отчёте real-document прогона и строки `run_glossary_*` в его summary,
   одно уведомление на экране результата с числом терминов.

Сбой прохода не роняет прогон и не становится гейтом: перевод идёт без глоссария, а пользователь
и отчёт это видят. Измерение — два evidence-скрипта: полнота кандидатов против терминологических
списков рецензентов и согласованность передач по `pairs.jsonl` (инструмент SC-006).

## Technical Context

**Language/Version**: Python 3.13 в WSL Debian (`.venv`), канонический раннер `scripts/test.sh`.

**Primary Dependencies**: только стандартная библиотека (`re`, `math`, `collections`) для
извлечения; существующий провайдерный путь текстовой модели (`generation/_generation.py`:
Responses API → OpenRouter Chat Completions fallback → Anthropic Messages).

**Storage**: новый каталог `.run/run_glossaries/` (TTL 14 дней, не больше 200 файлов) по правилам
`docs/LOGGING_AND_ARTIFACT_RETENTION.md` §5.4.

**Testing**: pytest через `scripts/test.sh`; новый модуль тестов `tests/test_glossary_pass.py`,
плюс точечные тесты в существующих модулях (конфиг, рендер профиля, пайплайн, раннер, UI).

**Target Platform**: тот же процесс Streamlit/фоновый воркер и раннер real-document прогонов.

**Project Type**: одно Python-приложение.

**Performance Goals**: извлечение кандидатов на книге — секунды, а не минуты (прототип: ~1 с на
книгу после построения индекса n-грамм; первая наивная версия с регэкспом на кандидата — 97 с на
четыре книги, поэтому индекс обязателен); один вызов модели на прогон.

**Constraints**: Конституция VII — ни одного списка терминов или литерала книги в репозитории;
сигналы только типографские (регистр, курсив, кавычки), статистические по самому документу,
региональные и грамматика конструкций определения (research R3). Fail-open. Ни одного нового
гейта. Промпт блока растёт в пределах бюджета (по умолчанию 3 000 символов).

**Scale/Scope**: 1 250–1 740 абзацев прозы на книгу корпуса, 400 кандидатов, до 60 терминов в
глоссарии, 280–715 текстовых вызовов на книгу, получающих глоссарий.

## Constitution Check

### До проектирования

- **I/II — PASS.** Все проверки — `scripts/test.sh` через `wsl.exe`; evidence-скрипты — в WSL;
  офлайн-счёт по `pairs.jsonl` — `python3 -I` без импорта репозитория.
- **III — PASS.** Новый проход и новый контракт данных → полный цикл; `plan.md` и `tasks.md`
  коммитятся до кода.
- **IV — неприменимо**: это не разбор упавшего real-document прогона; числа ревью цитируются из
  `review/terminology.json` четырёх книг.
- **V — PASS.** Путь артефакта, события, retention, строки отчёта и summary заданы здесь и в
  `contracts/glossary.md`.
- **VI — PASS.** Затрагиваются: новый модуль, слот профиля, одна фаза пайплайна, три провайдерных
  хелпера (параметр стадии учёта), конфиг, раннер, одно уведомление UI. `block_execution.py`,
  `operation_translate.txt`, `semantic_blocks.py`, `output_validation.py`, `document/` импорт —
  НЕ трогаются (их делят параллельные ветки P1).
- **VII — PASS с аргументом (research R3).** Списка терминов нет и не появляется; глоссарий
  строится из документа во время прогона и живёт в его артефактах. Богословский список не
  расширяется и образцом не служит (FR-016): он остаётся отдельным входом. Единственный
  языковой ресурс — шесть глаголов конструкции определения английского языка — того же рода,
  что признанный Конституцией «anchor lexicon» регионов: общий для книг, расширяемый по языкам,
  не литерал книги; на языке без этой грамматики сигнал просто отсутствует (принятый хвост).
  Проход не реконструирует структуру («no source signal, no repair» не задет): кандидат — это
  строка контекста для модели, а не роль абзаца, и ошибочный кандидат стоит одну строку
  промпта, которую модель вправе отбросить. Глоссарий — не верификатор и не гейт.
- **VIII — PASS.** База — прогоны 2026-11-07 на `f4d5562`; `src/` с тех пор менялся только P0
  (`4abb738`, сборка), который не трогает ни промпт, ни входы извлечения. Абзацы с регионами для
  замера пересняты 2026-11-07 текущим кодом подготовки (`e1f1aed`) без вызова модели
  (research R3, «Данные»).

### После проектирования

PASS. Проход живёт в пайплайне, внутри области учёта прогона, использует текстовый клиент и
модель прогона и пишет только в свои артефакты. Отказ — данные, а не вердикт. Исключений нет.

## Project Structure

### Documentation (this feature)

```text
specs/063-translation-fidelity/
├── spec.md              # общая спека 063 (P0…P3); P2 — FR-013…FR-016
├── plan.md              # этот файл — только P2
├── research.md          # решения R1…R9 и замер прототипа
├── data-model.md        # GlossaryCandidate, GlossaryTerm (расширение), RunGlossary
├── quickstart.md        # как проверить
├── contracts/glossary.md
└── tasks.md             # следующий шаг (speckit-tasks)
```

### Source Code (repository root)

```text
src/docxaicorrector/
├── text/glossary_pass.py            # НОВЫЙ: извлечение по форме, запрос, разбор ответа, вход домена
├── document/segments.py             # GlossaryTerm += kind, note; рендер по бюджету символов
├── processing/preparation.py        # домен-глоссарий через общий хелпер (поведение то же)
├── pipeline/glossary_phase.py       # НОВЫЙ: фаза прогона (применимость, вызов, артефакт, события)
├── pipeline/setup.py                # execute_processing_run: вызов фазы после инициализации
├── pipeline/_pipeline.py            # передача реализации фазы
├── pipeline/contracts.py            # ProcessingState: итог глоссария для уведомления
├── pipeline/late_phases.py          # уведомление result.run_glossary_*
├── generation/_generation.py        # usage_stage у трёх провайдерных хелперов + request_text_completion
├── core/model_accounting.py         # STAGE_GLOSSARY_EXTRACTION
├── core/config.py, config_runtime_sections.py, config_loader_layers.py  # 4 ключа glossary_*
├── runtime/artifact_retention.py    # RUN_GLOSSARIES_MAX_AGE_SECONDS / _MAX_COUNT
├── ui/_ui.py, ui/locales/{ru,en}.json  # вид уведомления "glossary"
└── resources/config.toml, resources/prompts/glossary_extraction.txt (НОВЫЙ)
.env.example
tests/artifacts/real_document_pipeline/run_lietaer_validation.py  # секция run_glossary + summary
scripts/measure-glossary-candidates.py       # НОВЫЙ evidence (WSL, без модели; --live — один вызов)
scripts/measure-glossary-consistency.py      # НОВЫЙ evidence (python3 -I, без импорта репозитория)
scripts/README.md, docs/LOGGING_AND_ARTIFACT_RETENTION.md
tests/test_glossary_pass.py (НОВЫЙ) + точечные тесты в test_config.py, test_document_pipeline.py,
  test_app.py, test_real_document_pipeline_validation.py, test_runtime_artifact_retention.py
```

**Structure Decision**: чистое извлечение и контракт ответа модели — в слое `text/` рядом с
`translation_domains.py` (это тот же вопрос — терминология), без зависимостей от пайплайна;
решение «когда запускать и что делать с итогом» — в отдельной фазе `pipeline/glossary_phase.py`,
вызываемой из `execute_processing_run` так же, как остальные фазы (через параметр-функцию, чтобы
тестовые двойники, не знающие о фазе, работали без изменений). Почему не в подготовке и почему не
через проводку профиля в пайплайн — research R1 и R2.

## Порядок изменений (почему он важен)

1. Контракт записи (`GlossaryTerm` + рендер по бюджету) — до всего: на нём стоят и проход, и
   богословский путь. Анти-регресс богословского пути проверяется на этом шаге.
2. Извлечение кандидатов — чистая функция, тестируется синтетическими абзацами.
3. Запрос/ответ модели и провайдерный хелпер со стадией учёта.
4. Конфиг (ключи и их значения по умолчанию): фаза читает ключи, поэтому конфиг идёт раньше неё.
5. Фаза пайплайна (применимость, fail-open, артефакт, события) и проводка в `execute_processing_run`.
6. Видимость: уведомление UI, раннер, документация логов.
7. Evidence-скрипты, замер на четырёх книгах, один живой вызов (≤ $0,50).

## Complexity Tracking

Нарушений Конституции нет. Одно осознанное усложнение — второй рендер-раздел глоссария в
`document_context_prompt` вместо записи в профиль подготовки; почему — research R2.
