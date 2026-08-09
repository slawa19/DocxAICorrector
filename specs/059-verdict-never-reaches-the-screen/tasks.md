# Tasks: остаток части A спеки 059

**Branch**: `feat/059-part-a-completeness-contract` | **Date**: 2026-08-09
**Input**: [spec.md](spec.md), [plan.md](plan.md), [measurement-translation-signal.md](measurement-translation-signal.md)

Порядок **обязателен**: A-0 → A-I → A-II → A-4 → FR-A9. Спека объясняет почему (`spec.md:384-386`),
anti-regression #10 требует это доказать. Каждая задача с тестом: **тест пишется первым, запускается,
падает, и только потом чинится код.**

## Фаза 0 — основание замера (A-0)

- [x] **T001** `scripts/measure-block-pair-rule.py`: правило пары, посчитанное на БЛОКАХ
  (`call_index` дампа) по пяти прогонам. stdlib, без сети и без LLM, `SKIPPED` без gitignored
  дампов. Печатает поимённо каждое срабатывание.
- [x] **T002** Результат замера записан в `plan.md` («Что замер добавил к спеке до начала кода»):
  1 срабатывание на 1 389 блоков, единственное — front matter.

## Фаза I — A-I: признак доходит до места решения

- [ ] **T010** [test-first] `tests/test_document_pipeline_output_validation.py`: правило пары на
  уровне классификации. Вход — блок, чей доставленный текст побайтово равен исходнику и короче
  прежнего пола `_SOURCE_TEXT_FALLBACK_MIN_CHARS`. Сегодня `classify_processed_block` возвращает
  `valid`. Тест обязан упасть.
- [ ] **T011** [test-first] Тот же файл: полностью английский ответ, РАВНЫЙ исходнику, без
  кириллицы и короче двенадцати английских слов → `source_text_fallback`. Сегодня `valid`.
- [ ] **T012** [test-first] FR-A5: при `languages_differ=False` тот же вход остаётся `valid`
  (ru→ru — 65,0 % законных совпадений, §5 замера).
- [ ] **T013** [test-first] Anti-regression #13: тест на ОТСУТСТВИЕ пятисловного словаря —
  `has_unexplained_english_residuals` и множество `{"chapter","contents","introduction",
  "conclusion","judgment"}` не существуют в `pipeline.output_validation`. Сегодня существуют.
- [ ] **T014** [test-first] FR-A2: побайтовое сравнение реализовано ОДИН раз —
  `block_execution.fallback_delivered_source_text` и
  `output_validation.is_source_text_fallback_output` дают одинаковый ответ на одной и той же паре,
  и `fallback_delivered_source_text` перестаёт иметь ровно одного потребителя.
- [ ] **T015** Код: `output_validation.delivered_text_equals_source` — единственная реализация
  сравнения; `is_source_text_fallback_output` = равенство + буква в исходнике; удалить
  `_SOURCE_TEXT_FALLBACK_MIN_CHARS`, `_SOURCE_TEXT_FALLBACK_MIN_ENGLISH_WORDS`.
- [ ] **T016** Код: `classify_processed_block(..., *, languages_differ: bool = True)`; удалить
  `has_unexplained_english_residuals` и его множество; статус `english_residual_output` оставить в
  типе и таблице решений.
- [ ] **T017** Код: `block_execution.fallback_delivered_source_text` делегирует в
  `delivered_text_equals_source`; докстрока называет это единственной реализацией.
- [ ] **T018** Код: `block_execution.process_single_block` и шов `_pipeline._classify_processed_block`
  передают `languages_differ`, вычисленный из `context.source_language`/`target_language`.
- [ ] **T019** Обновить голден `tests/fixtures/output_validation_characterization/
  classify_processed_block.json` (осознанное изменение поведения; диффом — в отчёте).
- [ ] **T020** [test] Тест-характеризация остатка слепоты (расхождение со спекой, `plan.md`):
  связный английский ответ, НЕ равный исходнику, остаётся `valid`, с докстрокой на FR-A3 и §11.

## Фаза II — A-II: пер-абзацный регион до payload

- [ ] **T030** [test-first] `tests/test_document_structure_blocks.py`: `build_editing_jobs`
  выдаёт `paragraph_regions`, параллельный `paragraph_ids`, с `front_matter` на титульных абзацах,
  `toc` на абзацах с TOC-ролью, `back_matter` на блоках из reference-региона и `prose` на теле.
  Сегодня ключа нет — тест обязан упасть.
- [ ] **T031** [test-first] `tests/test_document_pipeline_output_validation.py`:
  `parse_processing_job` переносит `paragraph_regions` в `BlockExecutionPayload`; неизвестное
  значение региона — ошибка разбора, а не тихое «проза».
- [ ] **T032** Код: словарь регионов в `core/models.py`.
- [ ] **T033** Код: `document/semantic_blocks.py:build_editing_jobs` считает регионы;
  front matter — через `_resolve_source_front_matter_boundary` (переиспользование, не второе
  правило).
- [ ] **T034** Код: `pipeline/contracts.py:BlockExecutionPayload.paragraph_regions`,
  `pipeline/job_parsing.py` разбирает поле.
- [ ] **T035** Код: `block_execution.payload_contains_prose` — «хотя бы один абзац прозы»;
  `None` = регион неизвестен = считается прозой.

## Фаза III — A-4: инвариант таблицы решений

- [ ] **T040** [test-first] Anti-regression #7: для каждого из семи качественных видов на блоке
  ПРОЗЫ, чей доставляемый текст равен исходнику, решение не равно `fallback_continue`. Сегодня
  равно — тест обязан упасть.
- [ ] **T041** [test-first] Anti-regression #8 (анти-вакуум): тот же вход, но все абзацы блока —
  аппарат (`back_matter` / `toc` / `front_matter`) → `fallback_continue` сохраняется.
- [ ] **T042** [test-first] Anti-regression #7c: смешанный блок «аппарат + проза» → решение
  меняется, потому что в блоке ЕСТЬ проза; тот же блок без прозаического абзаца — не меняется.
- [ ] **T043** [test-first] Anti-regression #7b: измеренная контрольная группа. Блок целиком из
  строк, которые замер назвал ложными тревогами (`### B2B`, `MediCash, 165`,
  `www.triarchypress.com/peoplemoney`), в регионе аппарата → `fallback_continue`; и он же в
  регионе прозы, но в блоке с переведённым соседом → правило пары не срабатывает вовсе.
- [ ] **T044** [test-first] Anti-regression #10 (порядок): инвариант перестаёт срабатывать, если
  убрать регион (A-II) или предикат пары (A-I) — доказательство, что он не заявлен, а работает.
- [ ] **T045** [test-first] Anti-regression #3: ни один путь не убирает текст, который раньше
  доставлялся. Блок, доставлявшийся под `fallback_continue` и не подпадающий под инвариант,
  доставляется тем же текстом; при `fail` доставки нет вовсе — падает прогон, а не текст.
- [ ] **T046** Код: инвариант в `classify_processed_block_failure_decision`, включая
  `fail_reason`; десять структурных видов не трогаются.
- [ ] **T047** Код: событие `block_untranslated_prose_rejected` и счётчик
  `untranslated_prose_block_rejections`; запись в `docs/LOGGING_AND_ARTIFACT_RETENTION.md`
  (Конституция V).

## Фаза IV — FR-A9: дыра в озвучке

- [ ] **T050** [test-first] Ветка `block_execution.py:986-1005` при `languages_differ=False`
  перестаёт выбрасывать текст: законно неизменённый блок ru→ru попадает в `narration_chunks`.
  Сегодня выбрасывается — тест обязан упасть.
- [ ] **T051** [test] Anti-regression #11: неспасённый абзац остаётся `omitted`, а не
  `source_restored` (тест на СТАТУС, а не на текст).
- [ ] **T052** Код: условие ветки получает «задание меняет язык».
- [ ] **T053** Перечислить в отчёте ВСЕ пути в ветку `:988-991` после инварианта, с трассировкой
  по коду. «По построению недостижимо» без перечисления не принимается.

## Фаза V — закрытие

- [ ] **T060** Мутационная проверка каждого нового правила: сломать → назвать упавший тест →
  откатить.
- [ ] **T061** Полный набор, статический ярус, храповик pyright — зелёные; числа в отчёте.
- [ ] **T062** `git status --porcelain` пуст, мутации откачены, коммиты осмысленные.
