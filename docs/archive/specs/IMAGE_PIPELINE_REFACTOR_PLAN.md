# Спецификация: рефакторинг и переключение image pipeline на delivery-first архитектуру

> Статус: archived refactor-wave tracker. Документ фиксирует план и исторический ход cleanup-волны, а не заменяет текущий пользовательский contract режимов из `README.md` и `docs/WORKFLOW_AND_IMAGE_MODES.md`.

## 0. Цель

Перевести обработку изображений в DOCX на новый pipeline, в котором выбранный пользователем режим реально влияет на итоговые байты изображения в документе, а legacy-guardrails больше не затирают результат генерации без hard-failure причины.

Документ фиксирует:

1. результаты code review текущей реализации;
2. целевую архитектуру;
3. детальный план рефакторинга с порядком внедрения;
4. список устаревших веток и контрактов, подлежащих удалению;
5. критерии приемки.

### 0.1. Текущий статус на 2026-03-10

На момент актуализации плана в кодовой базе уже реализована часть delivery-first архитектуры:

- введён `image_pipeline_policy.py`, и orchestration в `image_pipeline.py` уже использует `build_generation_analysis()`, `should_attempt_semantic_redraw()` и `should_deliver_redrawn_candidate()`;
- `document_pipeline.py` и `processing_runtime.py` уже вынесли часть orchestration из `app.py`;
- multi-attempt semantic redraw, soft-accept, vision validation, deterministic reconstruction и prompt registry уже существуют как реальные runtime-компоненты.

При этом план ниже остаётся актуальным, но требует уточнения по фактическим хвостам:

- `compare_all` всё ещё реализован отдельной orchestration-функцией, но уже использует общий typed variant contract и per-variant validation primitives;
- mode resolution уже централизован в policy layer и не дублируется в `image_generation.py`;
- final delivery decision уже вынесен в `image_pipeline_policy.py`;
- `app.py` уже очищен от compare-all apply flow и большей части runtime helper logic;
- legacy `free` убран из runtime-кода и основных UI/docs;
- в артефактах подтверждены legacy suffix names вида `*_output.*`, тогда как `*_free_output.*` в текущем репозитории уже не подтверждаются.

### 0.2. Дополнение по second-pass audit

По дополнительному аудиту A-F подтверждены и скорректированы следующие остаточные хвосты refactor wave:

- устранено дублирование low-level image helpers: MIME detection, supported-image checks, JSON parsing, score clamp и retry wrapper вынесены в `image_shared.py`;
- удалён второй competing soft-accept path в `image_pipeline.py`: orchestration больше не переопределяет решение policy layer повторным threshold-set'ом;
- удалён dead config `prefer_structured_redraw` из runtime config surface и тестов;
- удалён dead field `ImageAsset.reconstruction_scene_graph`;
- `document.resolve_final_image_bytes()` теперь имеет явный контракт для `selected_compare_variant == "original"`;
- legacy artifact suffix в `tests/test_real_image_pipeline.py` переведён с `_output.*` на `_candidate.*`;
- в `image_generation.py` убрано повторное mode resolution, а adaptive API fallback loops получили finite retry cap.

Решения по финальному закрытию wave:

- runtime полностью переведён на validator-only contract `validate_redraw_result()`; delivery application живёт только в orchestration-layer `image_pipeline.py`;
- semantic generation требует explicit client на уровне runtime и тестов; скрытый fallback client из generation layer удалён;
- physical package split формально отложен отдельным decision gate: текущая flat-структура признана допустимой для этого этапа, так как логические границы слоёв уже зафиксированы контрактами, DI и прямыми unit/integration tests.

### 0.3. Трекинг замечаний A-F

Ниже зафиксирован поштучный статус подтверждённых замечаний. Этот раздел является рабочим трекером до полного закрытия wave.

#### A. Дублирование кода

- `A1` `_detect_mime_type`: подтверждено, исправлено. Общий helper вынесен в `image_shared.py`, локальные копии в analysis/validation/reconstruction убраны, generation переведён на shared helper.
- `A2` `_call_responses_create_with_retry`: подтверждено, исправлено. Общая retry-обёртка вынесена в `image_shared.py`.
- `A3` `_parse_json_object`: подтверждено, исправлено. Общий parser вынесен в `image_shared.py`.
- `A4` `_clamp_score`: подтверждено, исправлено. Общий clamp вынесен в `image_shared.py`; analysis/validation/config используют единый helper.
- `A5` `_is_supported_image_bytes`: подтверждено, исправлено. Общий helper вынесен в `image_shared.py`, локальные вызовы сведены к нему.

#### B. Архитектурные и контрактные замечания

- `B1` двойная soft-accept семантика: подтверждено, исправлено. Конкурирующий путь `try_soft_accept_semantic_candidate()` удалён, orchestration больше не переопределяет policy outcome вторым набором порогов.
- `B2` `semantic_soft_accept_*` не управляются config/env: подтверждено, исправлено удалением. После удаления второго soft-accept path эти ключи больше не используются runtime-кодом.
- `B3` `prefer_structured_redraw` dead config: подтверждено, исправлено. Ключ удалён из runtime config surface и тестов.
- `B4` `resolve_generation_mode` вызывается дважды: подтверждено, исправлено. Повторный вызов убран из generation layer, неиспользуемый export удалён из policy layer.
- `B5` несогласованность `analysis` vs `generation_analysis`: подтверждено, исправлено по корню вместе с `B4`. Generation больше не делает повторное mode-gating на переданном analysis.
- `B6` `reconstruction_scene_graph` никогда не заполняется: подтверждено, исправлено. Поле удалено из `ImageAsset`.
- `B7` `hasattr(asset, "validation_result")` избыточен: подтверждено, исправлено. Проверка удалена.

#### C. Тестовые пробелы

- `C1` нет прямых unit-тестов на policy layer: подтверждено, исправлено. Добавлены прямые тесты на `should_attempt_semantic_redraw`, `build_generation_analysis`, `is_advisory_safe_fallback`, `is_hard_validation_failure`, `resolve_validation_delivery_outcome`.
- `C2` нет теста на `try_soft_accept_semantic_candidate`: подтверждено, закрыто удалением объекта тестирования. Функция удалена вместе с `B1`.
- `C3` нет теста на `score_semantic_candidate`: подтверждено, исправлено. Добавлен прямой unit-тест.
- `C4` нет тестов на `_prepare_compare_variants` и `_build_compare_variant_candidate`: подтверждено, исправлено. Добавлены прямые unit-тесты.
- `C5` нет теста на compare apply для `selected_variant == "original"`: подтверждено, исправлено.

#### D. Потенциальные баги и edge cases

- `D1` неявный fallback при `selected_compare_variant == "original"`: подтверждено, исправлено. Контракт в `resolve_final_image_bytes()` сделан явным.
- `D2` O(width×height) BFS в background normalization: подтверждено, исправлено. Python BFS заменён на downsampled mask + `ImageDraw.floodfill()`/Pillow-пайплайн с последующим upsample, что убирает прежний Python-level performance hotspot.
- `D3` визуально неочевидный fallback-chain в `_generate_semantic_candidate`: подтверждено, исправлено. Flow разведен на явную structured-ветку и явную creative -> direct -> structured fallback-цепочку с обязательным explicit client и отдельными логами на каждом переходе.
- `D4` unbounded adaptation retries в `_call_images_edit/_call_images_generate`: подтверждено, исправлено. Добавлен finite cap на adaptation retries.

#### E. Legacy и документационный шум

- `E1` `_output.*` artifact pattern: подтверждено, исправлено. Паттерн в real-image test artifacts переименован в `_candidate.*`.
- `E2` исторические `free` упоминания в документации: подтверждено как допустимый doc-legacy. Runtime cleanup уже выполнен; документационные упоминания сохраняются только как исторический контекст.

#### F. Структурные замечания относительно целевой архитектуры

- `F1` `image_validation.py` всё ещё совмещает validation и delivery application: подтверждено, исправлено. Runtime и тесты переведены на validator-only contract; delivery application остаётся только в orchestration-layer.
- `F2` generation layer знает про config fallback client: подтверждено, исправлено. Semantic generation принимает только explicit client; скрытый fallback удалён из runtime и тестового surface.
- `F3` физическая декомпозиция в package не начата: подтверждено, закрыто decision gate. Для этой wave package split сознательно отложен; flat-layout признан допустимым до отдельной structural wave, поскольку логические границы модулей уже стабилизированы контрактами и тестами.

---

## 1. Findings code review

### F1. Пользовательский image mode не является главным источником истины

Проблема:
- UI передает `safe` / `semantic_redraw_direct` / `semantic_redraw_structured` / `compare_all` корректно;
- но дальше `image_analysis.py` и `image_validation.py` могут полностью переопределить пользовательское решение;
- в итоге пользователь переключает режим, а в итоговом DOCX получает тот же `safe` или `original`.

Причина:
- forced downgrade в `image_analysis.py` через `dense_text_bypass` и `dense_non_latin_text_bypass`;
- strict fallback в `image_validation.py`, который остается обязательным для delivery, а не advisory;
- single-mode semantic delivery зависит не от выбранного режима, а от цепочки `analysis -> candidate -> validator -> fallback`.

Следствие:
- режимы визуально "не работают" на реальных документах;
- новый generation-first pipeline существует, но не доминирует над legacy gatekeeping.

### F2. В коде смешаны три разных слоя ответственности

Сейчас в одном потоке смешаны:

1. routing:
   - определение допустимости redraw;
   - smart bypass;
   - mode normalization;
2. generation:
   - safe enhancement;
   - structured/direct generation;
   - deterministic reconstruction fallback;
3. delivery policy:
   - что вставлять в DOCX;
   - когда fallback обязателен;
   - когда validator только advisory.

Следствие:
- поведение трудно читать и трудно менять локально;
- любая новая ветка порождает перекрестные зависимости между `image_analysis.py`, `image_generation.py`, `image_pipeline.py`, `image_validation.py`, `document.py`.

### F3. `compare_all` реализован отдельной логикой, а не как частный случай общего delivery flow

Проблема:
- single-mode path и compare-all path собирают результат по разным правилам;
- compare-all требует дополнительную ручную пересборку DOCX;
- логика выбора и логика reinsertion разделены между `app.py`, `ui.py`, `document.py`, `image_pipeline.py`.

Следствие:
- поведение сложно объяснять пользователю;
- есть риск регрессий, когда single-mode и compare-all расходятся по контракту.

### F4. `app.py` все еще слишком толстый orchestration-layer

Проблема:
- `app.py` содержит UI orchestration, background runtime wiring, compare-all apply flow, image pipeline façade, document pipeline façade;
- это не точка входа, а еще один бизнес-модуль.

Следствие:
- изменение image flow требует трогать `app.py` даже там, где это не должно быть нужно;
- сложно тестировать и сопровождать.

### F5. В проекте сохранились legacy-названия и исторические артефакты

Проблема:
- в коде и документации еще видны старые сущности вроде `free`, `_output.*`, `free-mode`;
- в коде долгое время coexist'или старый strict fallback flow и новый generation-first flow.

Следствие:
- высокий когнитивный шум;
- разработчик не может быстро понять, какие имена и пути считаются каноническими.

---

## 2. Целевой архитектурный принцип

Новый pipeline должен быть **delivery-first**:

1. пользователь выбирает режим;
2. pipeline строит candidate согласно этому режиму;
3. validator оценивает риск;
4. итоговое delivery-решение принимает отдельная policy layer;
5. fallback обязателен только при hard-failure, а не при любом heuristic mismatch.

Ключевая цель:
- semantic mode должен менять итоговый DOCX по умолчанию;
- validator остается quality-control слоем, а не total override слоем;
- compare-all должен жить поверх тех же delivery primitives.

---

## 3. Целевой модульный разрез

### 3.1. `image_analysis.py`

Оставить только:
- mime/visual heuristics;
- vision extraction;
- routing metadata;
- advisory smart-bypass signals.

Убрать из прямой ответственности:
- final delivery-decision;
- окончательное разрешение user mode.

Выходной контракт:
- `ImageAnalysisResult` описывает изображение и routing hints;
- `semantic_redraw_allowed=false` больше не означает автоматически "никогда не генерировать";
- smart bypass должен различать `hard_safe_only` и `advisory_safe_preferred`.

### 3.2. `image_generation.py`

Оставить только:
- safe generation;
- direct/structured generation;
- deterministic reconstruction fallback;
- image restoration and canvas normalization.

Убрать из прямой ответственности:
- режимную policy-логику высокого уровня;
- knowledge о compare-all;
- knowledge о validator fallback policy.

### 3.3. `image_validation.py`

Оставить только:
- Level 1 validation;
- generation of `ImageValidationResult`;
- classification of reasons and scores.

Убрать из прямой ответственности:
- final document delivery decision как таковой.

### 3.4. Новый слой `image_pipeline_policy.py`

Назначение:
- central point for delivery rules.

Должен решать:
- можно ли запускать semantic redraw, если analysis дал advisory bypass;
- какие validator outcomes являются hard-failure;
- когда semantic redraw можно доставлять несмотря на advisory mismatch;
- как compare-all использует те же policy primitives.

### 3.5. `image_pipeline.py`

Оставить как orchestration layer только для изображений:
- analyze;
- build candidate(s);
- validate;
- resolve final asset state.

Он не должен:
- сам знать детали UI;
- сам знать специфику Streamlit session state;
- сам знать document rebuild actions beyond returned `ImageAsset` state.

### 3.6. `document.py`

Оставить:
- extraction of inline images;
- placeholder integrity;
- final bytes resolution;
- reinsertion.

Расширять осторожно:
- только canonical image byte resolution contract;
- не добавлять туда routing или validation.

### 3.7. `app.py`

Вынести из `app.py`:
- compare-all apply flow;
- image-pipeline façade/wrappers;
- document processing orchestration wrappers.

`app.py` должен остаться entrypoint + Streamlit page composition, а не местом бизнес-логики пайплайна.

---

## 4. Новый контракт delivery decision

### 4.1. Single-mode semantic path

Для `semantic_redraw_direct` и `semantic_redraw_structured`:

1. user mode выбирается в UI;
2. pipeline обязан попытаться построить candidate этого режима;
3. advisory dense-text bypass не отменяет попытку автоматически;
4. validator строит `ImageValidationResult`;
5. policy layer решает:
   - `accept` -> deliver redraw;
   - `soft-accept` / advisory accept -> deliver redraw с warning metadata;
   - `hard-failure` -> fallback safe/original.

### 4.2. Compare-all path

`compare_all` должен рассматриваться как расширение single-mode flow:

1. pipeline готовит `safe`, `semantic_redraw_direct`, `semantic_redraw_structured`;
2. каждый вариант проходит одинаковые primitives generation/validation;
3. compare layer только хранит выбор пользователя;
4. reinsertion использует единый `resolve_final_image_bytes()`.

### 4.3. Hard-failure definition

Hard-failure должен срабатывать только на:
- unreadable candidate;
- broken payload;
- validator exception;
- отсутствие candidate bytes;
- реальные системные ошибки pipeline.

Не считать hard-failure по умолчанию:
- низкий validator confidence;
- structure mismatch;
- text mismatch;
- advisory type drift;
- added entities heuristic.

Эти сигналы должны идти в telemetry, summary и spec-driven warnings, но не всегда ломать delivery.

Уточнение по текущему состоянию:
- в актуальном коде hard-failure пока шире и включает `image_type_changed`, `text_missing_in_candidate`, а также причины `missing_labels:*`;
- для закрытия этапа 1 нужно принять одно консистентное решение: либо сузить код до целевого списка выше, либо обновить документацию и тесты под текущую более строгую policy.

---

## 5. Что удалить как legacy

### 5.1. Legacy fallback semantics

Удалить концептуально:
- implicit assumption, что validator всегда важнее user-selected mode;
- forced-safe semantics для advisory dense-text cases.

### 5.2. Legacy naming

Нужно зачистить:
- `free` как рабочее внутреннее имя режима;
- неканонические artifact names вида `*_output.*`, если они не используются в текущих тестах и документации;
- упоминания `free-mode` в документации, в частности в UI/image-pipeline docs;
- исторические комментарии и формулировки, где `semantic_redraw_direct` описан как fallback/legacy branch без уточнения актуального статуса.

Важно:
- `*_free_output.*` больше не подтверждается в текущем репозитории и не должен оставаться отдельной обязательной cleanup-целью без повторной проверки.

### 5.3. Wrapper duplication

Убрать из `app.py` обертки, которые только пробрасывают зависимости без собственной логики, если они не нужны для тестирования или background/runtime isolation.

---

## 6. Детальный план реализации

### Этап 1. Stabilize delivery contract

Статус на 2026-03-10:
- реализован функционально, но не закрыт полностью.

Цель:
- сделать поведение режимов пользовательски наблюдаемым.

Шаги:
1. ввести policy layer для semantic delivery;
2. отделить advisory fallback от hard-failure;
3. разрешить semantic execution в advisory dense-text cases;
4. сохранить strict mode через конфиг для rollback.

Результат:
- direct/structured реально меняют итоговые image bytes;
- compare-all может подготовить semantic variants даже там, где старый bypass раньше все обнулял.

Оставшиеся задачи для закрытия этапа:
1. зафиксировать flat-модульную структуру как приемлемую альтернативу физическому package-split;
2. завершить cleanup legacy artifact references в тестовых артефактах и вспомогательных docs при следующем touch соответствующих файлов.

### Этап 2. Extract image pipeline package

Статус на 2026-03-10:
- физическая декомпозиция не начата;
- логические границы уже появились, поэтому этап теперь требует архитектурного решения, а не автоматического продолжения.

Цель:
- уменьшить связанность модулей.

Decision gate:
1. либо зафиксировать flat-структуру как приемлемую и ограничиться логическим разделением ответственности;
2. либо всё же вводить пакет `image_pipeline/` и переносить модули физически.

Целевая структура:

```text
image_pipeline/
├── __init__.py
├── analysis.py
├── generation.py
├── validation.py
├── policy.py
├── orchestration.py
└── contracts.py
```

Миграция:
1. перенести dataclass contracts и pure helpers;
2. разрезать `image_pipeline.py` на orchestration + policy helpers;
3. оставить compatibility exports на один переходный релиз.

### Этап 3. Unify compare-all with single-mode flow

Статус на 2026-03-10:
- завершён логически: `compare_all` использует typed variant contract, per-variant validation и единый final-bytes resolver; отдельная orchestration-функция остаётся допустимой реализационной деталью.

Цель:
- один delivery engine для всех режимов.

Шаги:
1. ввести общий `ImageVariantCandidate` contract;
2. single-mode path использовать как частный случай variant resolution;
3. compare-all хранить не raw dict'ы, а typed variant descriptors;
4. прогонять каждый compare-all вариант через generation + validation + delivery primitives, а не только через generation;
5. финальную вставку в DOCX всегда делать через единый resolver.

### Этап 4. Thin `app.py`

Статус на 2026-03-10:
- завершён по целевому acceptance scope: compare-all apply flow и runtime helper logic вынесены, `app.py` оставлен как entrypoint + page composition + action wiring.

Цель:
- убрать бизнес-логику пайплайна из точки входа.

Шаги:
1. вынести compare-all apply/rebuild в отдельный application service;
2. заменить helper/wrapper-слой в `app.py` прямыми вызовами там, где он больше не даёт test/runtime isolation;
3. сократить `app.py` до page composition и action wiring.

### Этап 5. Cleanup and docs normalization

Статус на 2026-03-10:
- завершён по runtime/UI/docs scope: канонические режимы синхронизированы, legacy `free` и `free-mode` убраны из runtime-кода и основных UI docs.

Цель:
- убрать старые имена и следы legacy behavior.

Шаги:
1. удалить stale artifact references и suffix naming вида `*_output.*`, если они не нужны как текущий test contract;
2. синхронизировать README, UI docs и tests с каноническими режимами `safe`, `semantic_redraw_direct`, `semantic_redraw_structured`, `compare_all`;
3. убрать `free` и `free-mode` из кода и docs;
4. описать advisory vs strict policy в docs и config.

---

## 7. Acceptance criteria

### Поведенческие критерии

1. `semantic_redraw_direct` и `semantic_redraw_structured` при успешной генерации меняют итоговое изображение в DOCX, если нет hard-failure.
2. `compare_all` готовит semantic variants даже для advisory dense-text bypass cases.
3. каждый compare-all вариант либо проходит через те же generation/validation primitives, что и single-mode path, либо это исключение явно документировано как временный technical debt.
4. `safe` остается строго non-generative режимом.
5. strict mode по конфигу сохраняет legacy fallback semantics для rollback.

### Архитектурные критерии

1. delivery policy выделена в отдельный модуль;
2. анализ, генерация, валидация и delivery policy больше не смешаны в одной функции;
3. `app.py` не содержит image-delivery decision logic и compare-all apply flow;
4. mode resolution не дублируется между policy и generation layer.

### Тестовые критерии

1. есть unit tests на advisory vs strict policy;
2. есть integration test, что semantic mode выполняется при advisory dense-text bypass;
3. есть smoke test на compare-all variant preparation;
4. есть test на per-variant validation или явно зафиксированное временное исключение для compare-all;
5. есть config tests на `semantic_validation_policy`.

---

## 8. Порядок внедрения без лишнего риска

1. Сначала стабилизировать runtime behavior и тесты.
2. Затем выделить policy module и orchestration boundaries.
3. После этого делать физическую декомпозицию файлов.
4. Только затем удалять compatibility layers и legacy artifact references.

Это важно: если начать с файловой декомпозиции до стабилизации delivery contract, проект получит большой diff без гарантии, что пользовательские режимы действительно начали работать.
