# Спецификация remediation по итогам code review — DocxAICorrector

**Дата:** 2026-03-16  
**Статус:** Реализовано и подтверждено тестами  
**Источник истины:** завершённый end-to-end code review upload boundary, preparation flow, document pipeline и image pipeline  
**Назначение документа:** превратить уже подтверждённые выводы review в практическую спецификацию внедрения без повторной интерпретации исходных замечаний

---

## 1. Цель спецификации

Этот документ фиксирует **план работ уровня implementation-spec** для remediation-работ после уже завершённого end-to-end code review.

Цель спецификации:

- закрыть подтверждённые разрывы boundary-контрактов без добавления новых product features;
- устранить silent corruption и false success-path в document pipeline и image pipeline;
- выровнять инварианты между upload boundary, preparation, processing runtime и downstream pipeline;
- задать безопасный порядок внедрения, при котором сначала усиливаются границы и тесты, затем ужесточаются контракты, затем выполняется hardening image pipeline, и только после этого допускается ограниченная архитектурная очистка.

Ключевой принцип: **сначала сделать поведение проверяемым и детерминированным, затем делать его удобнее и чище архитектурно**.

Важно: это именно **план изменений**, а не отчёт о завершённой реализации. Все формулировки ниже описывают требуемое целевое состояние и ожидаемые шаги внедрения.

---

## 2. Область действия

### 2.1 Что входит в спецификацию

В эту спецификацию входят только подтверждённые проблемы и уже обоснованные выводы review:

1. **Upload boundary и preparation boundary**
   - передача live upload-object через фоновую границу;
   - слабый marker идентичности файла на основе `name/size` вместо content hash;
   - несогласованная background error handling;
   - недостаточная archive-level validation до глубокого разбора DOCX.
2. **Основной document pipeline**
   - неполная проверка полноты placeholder integrity map;
   - маскировка битых jobs через `str(None)`;
   - позиционный перенос paragraph formatting после structural drift;
   - отсутствие строгой сверки фактически обработанного количества jobs.
3. **Image pipeline**
   - неполный учёт retryable API attempts в budget;
   - ложный success в `compare_all` при неполном наборе вариантов;
   - потеря уже готового safe fallback в semantic branch с откатом к original;
   - некорректная обработка украинских букв `і/ї/є/ґ` в validator.
4. **Поддерживающие архитектурные выводы review, которые обязаны быть отражены в плане внедрения**
   - перегруженность orchestration-логикой в `app.main()`;
   - слабая типизация boundary-контрактов между `preparation.py`, `application_flow.py`, `document_pipeline.py`, `processing_service.py`;
   - дублирование retry/budget semantics между `image_shared.py` и `image_generation.py`;
   - performance smell с повторной пересборкой markdown и копированием промежуточных chunks в `document_pipeline.py`;
   - пробелы в тестах по всем уже подтверждённым сценариям отказа и частичной деградации.

### 2.2 Что не входит в спецификацию

Вне рамок этой спецификации:

- новые user-facing features;
- UI redesign;
- замена модели OpenAI или смена провайдера;
- полный redesign DOCX semantic reconstruction сверх уже подтверждённых проблем;
- общая performance-оптимизация, не связанная напрямую с перечисленными замечаниями review;
- произвольная декомпозиция модулей без привязки к remediation-работам из этого документа.

---

## 3. Допущения и ограничения

### 3.1 Допущения

- Приложение остаётся Python-based Streamlit workflow с background processing.
- DOCX остаётся основным входным и выходным форматом.
- Основной safety net внедрения — существующие тесты в `tests/` с обязательным расширением покрытия под подтверждённые сценарии.
- Review findings из родительской задачи являются authoritative baseline и имеют приоритет над старыми планами и устаревшими markdown-описаниями.

### 3.2 Ограничения

- В рамках этой задачи изменяется только данный файл.
- Следующий implementation-этап должен по возможности избегать_Oneоментного слома текущих публичных точек входа.
- На этапе hardening предпочтителен путь `сначала добавить строгую валидацию и адаптеры`, а не одномоментная массовая перестройка архитектуры.
- Там, где есть выбор между silent degradation и explicit degraded or failed outcome, внедрение должно смещаться в сторону **явного статуса**.

### 3.3 Не-цели следующего implementation-этапа

- Не требуется достигнуть идеального архитектурного end-state за один проход.
- Не требуется сразу переписать весь pipeline вокруг новых dataclass-объектов.
- Не требуется устранять гипотетические проблемы, которые не подтверждены review-контекстом.

---

## 4. Приоритеты и корзины внедрения

### 4.1 Каталог приоритетов

| ID | Приоритет | Корзина | Краткое описание |
|---|---|---|---|
| CR-01 | Critical | Must-fix before next feature work | Live upload-object пересекает background boundary |
| CR-02 | Critical | Must-fix before next feature work | Preparation marker основан на `name/size`, а не на content hash |
| CR-03 | Critical | Must-fix before next feature work | Background errors не нормализуются единым контрактом |
| CR-04 | Critical | Must-fix before next feature work | Archive-level DOCX/ZIP validation недостаточна до deep parse |
| CR-05 | Critical | Must-fix before next feature work | Placeholder integrity не проверяется на полноту и согласованность |
| CR-06 | Critical | Must-fix before next feature work | `str(None)` маскирует broken jobs |
| CR-07 | Critical | Must-fix before next feature work | No strict reconciliation of actually processed job count |
| HI-01 | High | Can-fix in subsequent hardening | Paragraph formatting is transferred positionally after structural drift |
| HI-02 | High | Can-fix in subsequent hardening | Retryable API attempts are undercounted in budget |
| HI-03 | High | Can-fix in subsequent hardening | `compare_all` can report false success with incomplete variants |
| HI-04 | High | Can-fix in subsequent hardening | Semantic branch loses already prepared safe fallback and drops to original |
| ME-01 | Medium | Can-fix in subsequent hardening | Ukrainian text validation mishandles Ukrainian letters `і/ї/є/ґ` |

### 4.2 Explicit delivery buckets

#### Must-fix before next feature work

- CR-01
- CR-02
- CR-03
- CR-04
- CR-05
- CR-06
- CR-07

#### Can-fix in subsequent hardening

- HI-01
- HI-02
- HI-03
- HI-04
- ME-01

#### Optional architectural cleanup

Межрутем это планируется отложить до после основного харднинга:

- ME-01
- AC-01
- AC-02

---

## 5. Detailed problem catalog by priority (complete)

### 5.1 Critical issues

---

### CR-01 — Live upload-object пересекает background boundary

**Симптом**

Background preparation и связанная orchestration-логика могут зависеть от live uploaded object вместо неизменяемого byte payload. Это делает поведение worker-запуска зависимым от времени жизни Streamlit-объекта и повторных rerun.

**Root cause**

The upload boundary is not frozen into an immutable payload before crossing into background execution. Runtime and application-flow code rely on an object that is valid in the UI/request boundary but not guaranteed to remain stable across async or threaded work.

**Affected files and functions**

- `app.py` — background start path
- `processing_runtime.py` — background preparation bootstrap
- `application_flow.py` — background run-context preparation

**Risk**

- Race-prone reads from a mutable or stale upload object;
- Non-deterministic preparation outcome after rerun or file reselection;
- Hidden failures when the worker can no longer read the upload object;
- Inability to reason about idempotency of preparation.

**Reproduction scenario**

1. User uploads a DOCX.
2. Background preparation starts.
3. Before worker finishes, UI reruns or selected file changes.
4. Worker continues reading through a live upload object seam instead of an immutable payload.
5. Preparation can observe stale, missing, or inconsistent bytes.

**Target behavior after fix**

- Background boundary accepts only an immutable upload payload.
- The payload includes at minimum raw bytes, original filename, file size, and content hash.
- All downstream preparation code reads from the frozen payload, never from a live Streamlit upload object.

**Expected code changes**

- Introduce a single immutable upload payload contract at the app/runtime boundary.
- Freeze upload bytes before scheduling background work.
- Remove or deprecate worker paths that accept a live upload object directly.

**Required tests**

- `tests/test_app.py`
- `tests/test_processing_runtime.py`
- `tests/test_application_flow.py`

---

### CR-02 — Preparation marker is based on `name/size` instead of content hash

**Симптом**

Different files with the same filename and size can collide in preparation state, shared cache, or progress tracking.

**Root cause**

Preparation identity is derived from weak metadata markers rather than content-addressed identity.

**Affected files and functions**

- `processing_runtime.py`
- `app.py`
- supporting preparation/cache key paths in `preparation.py`

**Risk**

- cache poisoning between different uploads;
- false cache hit or false resume/reuse;
- stale preparation result reused for the wrong document;
- hard-to-debug mismatches between visible file and prepared content.

**Reproduction scenario**

1. Prepare a DOCX named `report.docx` of size X.
2. Upload a different DOCX with the same name and same byte size.
3. Current marker logic treats them as equivalent or near-equivalent.
4. Preparation or worker state may be reused incorrectly.

**Target behavior after fix**

- Canonical preparation marker must be derived from content hash.
- Filename and size remain metadata only, not identity.
- Cache keys, worker progress identifiers, and restart markers use the same canonical identity contract.

**Expected code changes**

- Compute content hash once at the boundary when freezing upload payload.
- Thread the hash through runtime, preparation and state updates.
- Replace any remaining `name/size/file_id` identity logic with a content-addressed marker.

**Required tests**

- `tests/test_app.py`
- `tests/test_processing_runtime.py`
- `tests/test_preparation.py`

---

### CR-03 — Background error handling is degraded and not normalized

**Симптом**

Different background failure paths can surface inconsistent payload shapes, inconsistent user messages, or incomplete technical context.

**Root cause**

Preparation and processing background flows do not share a strict normalized error contract with common fields and common translation rules.

**Affected files and functions**

- `processing_runtime.py`
- `app.py`

**Risk**

- silent or partially silent failures;
- inconsistent UI status rendering;
- brittle worker-complete and worker-failure handling;
- poor diagnostics when a background worker crashes in a stage-specific way.

**Reproduction scenario**

Inject different failures into preparation and processing workers, such as malformed DOCX, budget exhaustion, internal assertion failure, and provider errors. Observe that user-facing and internal failure representation is not normalized.

**Target behavior after fix**

- All background errors are converted into a normalized error envelope.
- The envelope includes stage, severity, user-safe message, technical message, error type, and optional recoverability flag.
- App-level rendering consumes the normalized envelope instead of stage-specific ad-hoc payloads.

**Expected code changes**

- Add one shared normalization function for worker exceptions.
- Ensure both preparation and processing workers emit the same failure contract.
- Update app-level event draining and status rendering to consume only normalized worker failures.

**Required tests**

- `tests/test_processing_runtime.py`
- `tests/test_app.py`
- `tests/test_application_flow.py` where boundary-to-worker error routing is involved

---

### CR-04 — Archive-level DOCX/ZIP validation is insufficient before deep parse

**Симптом**

A DOCX can reach deeper preparation/parsing logic before enough archive-level checks have been applied at the boundary.

**Root cause**

Archive validation is not enforced early enough in the upload-to-preparation path, so deep parse is still responsible for rejecting malformed or abusive archives.

**Affected files and functions**

- `app.py`
- `processing_runtime.py`
- `preparation.py` (also application_flow, consider adding there)

**Risk**

- unnecessary deep parsing of invalid archives;
- higher memory and CPU cost before rejection;
- weaker boundary hardening for malformed ZIP/DOCX payloads;
- larger blast radius when malformed input reaches later stages.

**Reproduction scenario**

Use a malformed or hostile DOCX/ZIP that should fail at archive-level checks. Current flow allows it to enter deeper preparation work before rejection is finalized.

**Target behavior after fix**

- Boundary performs explicit archive-level validation before deep document preparation.
- Preparation never starts deep parse for a payload that already fails basic DOCX/ZIP archive safety and shape checks.
- Early validation result is surfaced consistently in foreground and background paths.

**Expected code changes**

- Introduce a shared early validation helper reused by foreground and background entry paths.
- Make `preparation.py` depend on prevalidated immutable input or revalidate via the same shared helper, not via diverging logic.
- Ensure validation is deterministic across app and worker entry points.

**Required tests**

- `tests/test_app.py`
- `tests/test_processing_runtime.py`
- `tests/test_preparation.py`

---

### CR-05 — Placeholder integrity map completeness is not fully enforced

**Симптом**

Document processing can continue even when placeholder integrity information is incomplete, one-sided, or inconsistent with actual placeholders that must be reinserted.

**Root cause**

Integrity checking is not treated as a full completeness and consistency contract between expected placeholders, observed placeholders, and reinsertion-ready mapping.

**Affected files and functions**

- `document_pipeline.py`
- `document.py`

**Risk**

- broken jobs appear superficially valid;
- downstream prompts and document assembly receive semantically invalid text;
- incomplete or corrupted final DOCX with missing image placements.

**Reproduction scenario**

Prepare a document where one placeholder is dropped, duplicated, or transformed during markdown conversion. Current integrity logic can miss the completeness failure or not escalate it strictly enough.

**Target behavior after fix**

- Placeholder integrity becomes a strict contract.
- Success requires full reconciliation between expected placeholder set and actual post-conversion placeholder set.
- Any mismatch is escalated to explicit degraded or failed status.

**Expected code changes**

- Define an explicit completeness check in `document.py`.
- Enforce it in `document_pipeline.py` before final output is marked successful.
- Distinguish between integrity pass, integrity degraded, and integrity failed states.

**Required tests**

- `tests/test_document_pipeline.py`
- `tests/test_document.py`
- targeted regression in `tests/test_image_integration.py` if placeholder/image reinsertion interplay is validated end-to-end (existing test exists)

---

### CR-06 — `str(None)` masks broken jobs and distorts contracts

**Симптом**

A broken job with `None` in a required text field can be silently coerced to the string `None`, allowing the pipeline to continue as if a valid string existed.

**Root cause**

Validation is happening after string coercion, instead of validating the nullable contract first and only then treating the value as a real string.

**Affected files and functions**

- `document_pipeline.py`

**Risk**

- broken jobs appear superficially valid;
- downstream prompts and document assembly receive semantically invalid text;
- debugging becomes harder because the original null-contract violation is hidden.

**Reproduction scenario**

Force one prepared or processed job to contain `None` in a required text/output field. The current logic stringifies it and can propagate `None` as user content.

**Target behavior after fix**

- Required text fields are validated as non-null before any string normalization.
- `None` remains a contract violation and is surfaced explicitly.
- Pipeline must fail or mark the run degraded rather than silently coercing nulls into content.

**Expected code changes**

- Replace string-coercion-first checks with explicit nullable checks.
- Centralize validation of required job fields in one document-pipeline helper.
- Ensure logging and error messages preserve the fact that the original value was null.

**Required tests**

- `tests/test_document_pipeline.py`

---

### CR-07 — No strict reconciliation of actually processed job count

**Симптом**

The pipeline can reach a success path without proving that the number of actually processed jobs matches the expected number of jobs to process.

**Root cause**

Success criteria are not tied tightly enough to the expected-vs-actual processing counts and per-job completion invariants.

**Affected files and functions**

- `document_pipeline.py`

**Risk**

- partial document processing reported as success;
- dropped blocks without explicit failure;
- downstream assembly operating on an incomplete set of processed chunks.

**Reproduction scenario**

Create a path where one job is skipped, filtered, short-circuited, or returns no usable output, but the pipeline still reaches the nominal success branch.

**Target behavior after fix**

- `success` requires exact reconciliation between expected jobs and actually completed jobs.
- Any mismatch is escalated to explicit degraded or failed status.
- Job count reconciliation happens before final output is emitted.

**Expected code changes**

- Add strict expected-count vs actual-count reconciliation in the main success path.
- Include failed, skipped, and incomplete counts in runtime outcome metadata.
- Keep user-visible outcome aligned with the actual processing completeness.

**Required tests**

- `tests/test_document_pipeline.py`
- supporting e2e confirmation in `tests/test_image_integration.py` where applicable (existing test exists)

---

### 5.2 High issues

---

### HI-01 — Paragraph formatting is transferred positionally after structural drift

**Симптом**

When markdown-to-DOCX conversion changes paragraph structure, formatting is still transferred positionally via `zip()`, causing formatting to land on the wrong paragraphs.

**Root cause**

Formatting transfer assumes source and target paragraph lists remain structurally aligned. After semantic rewriting, that assumption is not reliable.

**Affected files and functions**

- `document.py`

**Risk**

- silent formatting corruption;
- misapplied paragraph properties;
- visually valid but semantically misformatted output.

**Reproduction scenario**

Use content where generation splits one paragraph into two, merges neighboring paragraphs, or changes list structure. Positional transfer then misaligns formatting.

**Target behavior after fix**

Near-term hardening target:

- positional transfer must not run blindly when structural drift is detected;
- mismatch must be surfaced explicitly as degraded behavior or controlled skip;
- no silent positional formatting corruption.

Longer-term cleanup target:

- move toward anchor-based or block-based formatting transfer rather than raw positional `zip()`.

**Expected code changes**

- Add precondition checks around formatting transfer.
- Stop treating equal iteration length through `zip()` as evidence of valid alignment.
- Introduce a stricter mismatch policy and preserve enough metadata for future anchor-based transfer.

**Required tests**

- `tests/test_document.py`
- `tests/test_document_pipeline.py`
- Ensure structural drift detection is covered by targeted tests, including paragraph recombination scenarios.

---

### HI-02 — Retryable API attempts are undercounted in budget

**Симптом**

Retryable provider errors and parameter-adaptation retries can distort budget accounting, either spending budget too early or skipping consumption for a real final call.

**Target behavior after fix**

- Budget is checked before each external call attempt.
- Budget is consumed exactly once for the final effective API call outcome.
- Retryable adaptation and retry loops do not double-consume budget.

**Implemented state**

- `image_shared.py` consumes budget only on terminal failure or success.
- `image_generation.py` defers consumption until the effective call outcome for `images.edit`, `images.generate`, and `responses.create`.
- `image_reconstruction.py` routes scene-graph extraction through the shared retry helper with timeout and budget support.

**Required tests**

- `tests/test_generation.py`
- `tests/test_image_generation.py`
- `tests/test_image_reconstruction.py`

---

### HI-03 — `compare_all` can report false success with incomplete variants

**Симптом**

The compare-all path can expose partial variant sets while still looking like a successful compare outcome.

**Target behavior after fix**

- `compare_all` reports success only when the expected variant set is fully prepared.
- Incomplete compare-all preparation degrades explicitly to fallback status.
- UI compare controls render only for true compared assets.

**Implemented state**

- `image_pipeline.py` applies explicit incomplete-variant fallback.
- `compare_panel.py` renders only for assets with `validation_status == "compared"`.

**Required tests**

- `tests/test_image_pipeline_compare_helpers.py`
- `tests/test_image_integration.py`
- `tests/test_app.py`

---

### HI-04 — Semantic branch loses already prepared safe fallback and drops to original

**Симптом**

When semantic redraw fails late, the pipeline can discard an already prepared safe candidate and revert all the way to the original image.

**Target behavior after fix**

- If `safe_bytes` already exists, semantic failure paths prefer `fallback_safe`.
- Reversion to original is reserved for cases where no safe fallback exists.

**Implemented state**

- `image_pipeline.py` now preserves safe fallback for semantic budget exhaustion and validator/attempt failure paths.

**Required tests**

- `tests/test_image_integration.py`

---

### ME-01 — Ukrainian text validation mishandles Ukrainian letters `і/ї/є/ґ`

**Симптом**

Validation tokenization can falsely detect text loss or label mismatch for Ukrainian content.

**Target behavior after fix**

- Tokenization and normalization handle Ukrainian Cyrillic letters consistently in summaries and labels.

**Implemented state**

- `image_validation.py` now uses a shared token pattern that includes `ІіЇїЄєҐґ`.

**Required tests**

- `tests/test_image_validation.py`

---

### 5.3 Optional architectural cleanup

#### AC-01 — Reduce weakly typed orchestration boundaries

Near-term completion target for this remediation wave:

- strengthen boundary typing where it directly protects corrected contracts;
- avoid large-scale API churn outside the hardened paths.

Implemented in this wave:

- `processing_service.py` moved core service wiring away from `object` fields toward explicit protocol and callable types.
- immutable upload payload contract introduced at the app/runtime boundary.

Deferred beyond this wave:

- broader typing cleanup across all orchestration modules.

#### AC-02 — Reduce duplicated retry and budget semantics

Near-term completion target for this remediation wave:

- unify the highest-risk retry and budget paths first, especially those that affect image reconstruction and provider adaptation logic.

Implemented in this wave:

- scene-graph extraction now reuses the shared retry helper.
- image generation retry loops now follow the same consume-on-terminal-outcome semantics.

Deferred beyond this wave:

- full consolidation of all retry helpers into a single cross-module abstraction.

---

## 6. Implementation status

### 6.1 Completed in this remediation wave

- CR-01 — completed
- CR-02 — completed
- CR-03 — completed
- CR-04 — completed
- CR-05 — completed
- CR-06 — completed
- CR-07 — completed
- HI-01 — completed
- HI-02 — completed
- HI-03 — completed
- HI-04 — completed
- ME-01 — completed

### 6.2 Verified outcome

- Full visible verification completed via the VS Code task `Run Full Pytest`.
- Result: `349 passed, 4 skipped`.

### 6.3 Remaining work after this wave

- No confirmed must-fix or high-priority remediation items remain open from this specification.
- Further work, if needed, should be treated as a separate architecture or cleanup task rather than continuation of this remediation wave.
