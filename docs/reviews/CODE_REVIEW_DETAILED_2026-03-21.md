# Детальное расширенное код ревью

**Дата:** 2026-03-21  
**Scope:** universal real-document validation architecture, legacy `.doc` normalization, repeat/soak execution, regression hardening `heading_only_output`  
**Reviewed:** `processing_runtime.py`, `application_flow.py`, `document.py`, `corpus_registry.toml`, `real_document_validation_profiles.py`, `real_document_validation_structural.py`, `run_lietaer_validation.py`, `document_pipeline.py`, `formatting_transfer.py`, `generation.py`, `models.py`, `constants.py`, все связанные тест-файлы

---

## Оглавление

1. [Executive Summary](#1-executive-summary)
2. [Архитектурная оценка](#2-архитектурная-оценка)
3. [Критические находки (P0)](#3-критические-находки-p0)
4. [Серьёзные находки (P1)](#4-серьёзные-находки-p1)
5. [Замечания средней важности (P2)](#5-замечания-средней-важности-p2)
6. [Мелкие замечания и стиль (P3)](#6-мелкие-замечания-и-стиль-p3)
7. [Покрытие тестами](#7-покрытие-тестами)
8. [Спецификация vs реализация](#8-спецификация-vs-реализация)
9. [Итоговая матрица рисков](#9-итоговая-матрица-рисков)
10. [Рекомендации](#10-рекомендации)

---

## 1. Executive Summary

Changeset реализует архитектурно значимый набор изменений: registry-driven корпусную валидацию, нормализацию входных `.doc`-файлов, repeat/soak aggregation и regression coverage для `heading_only_output`. Общее качество реализации **хорошее** — чёткое разделение ответственности, defensive coding, хорошо структурированные error paths.

**Сильные стороны:**
- Чистая нормализационная граница: format detection → conversion → downstream contract
- Профильная система (document + run profiles) well-separated
- heading_only_output покрыт на трёх уровнях (pipeline, structural, full-tier)
- ZIP bomb protection и DOCX archive validation robust

**Основные риски:**
- Отсутствие subprocess timeout при `.doc` конверсии (зависание на malicious/corrupt файлах)
- Double/triple normalization при FrozenUploadPayload path (performance + fragility)
- OLE2 magic bytes не уникальны для DOC (XLS/PPT/MSG пройдут как "doc")
- Несколько critical test gaps (error paths, multi-block heading_only)
- `run_lietaer_validation.py` — 2032-строчный монолит с mixed concerns

---

## 2. Архитектурная оценка

### 2.1 Нормализационная граница (`processing_runtime.py`)

**Поток данных:**
```
Upload → _detect_uploaded_document_format() [magic bytes → extension fallback]
       → _convert_legacy_doc_to_docx() [soffice → antiword+pandoc fallback]
       → NormalizedUploadedDocument [всегда DOCX bytes]
       → freeze_uploaded_file() → FrozenUploadPayload [token, hash, bytes]
```

**Оценка: хорошо.** Нормализация происходит один раз, near payload ingestion. Все downstream consumers (document extraction, generation, formatting transfer, validation) работают с единым DOCX контрактом.

**Проблема:** Реально нормализация вызывается **до трёх раз** для одного `.doc` файла:
1. `freeze_uploaded_file()` → `normalize_uploaded_document()` — первичная конверсия
2. `_prepare_run_context_core()` → `normalize_uploaded_document()` — повторная (bytes уже DOCX, проходит как identity)
3. `build_uploaded_file_token()` → `normalize_uploaded_document()` — ещё раз при пересчёте токена

Для DOCX это identity pass-through (дешёво). Для DOC первый вызов конвертирует, последующие — identity. Корректность не нарушена, но это архитектурная fragility: любое изменение в `normalize_uploaded_document` должно учитывать идемпотентность.

### 2.2 Профильная система

**Двухуровневая структура:**
- `[[documents]]` — identity, structural expectations, acceptance thresholds
- `[[run_profiles]]` — execution parameters (tier, mode, repeat_count)

**Оценка: хорошо.** Чёткое разделение "что за документ" от "как его запускать". Resolution chain (explicit override → document default → error) простой и предсказуемый.

### 2.3 Structural validation determinism

**Passthrough job kind** (`_build_passthrough_job`) гарантирует determinism — no LLM calls, только format transfer. Extraction tier ещё проще — только чтение и извлечение, без pipeline.

**Оценка: хорошо.** Единственный risk — snapshot-diff для formatting diagnostics discovery (race condition при concurrent runs). Lietaer runner имеет 3-tier fallback (snapshot → event_log → recent_scan), но `structural.py` использует только snapshot.

### 2.4 Сквозной data flow

```
processing_runtime.normalize_uploaded_document()
  → document.extract_document_content_from_docx() → [ParagraphUnit], [ImageAsset]
    → document_pipeline.run_document_processing()
      → generation.generate_markdown_block() per block
      → generation.convert_markdown_to_docx_bytes()
      → formatting_transfer.preserve_source_paragraph_properties()
      → image_reinsertion.reinsert_inline_images()
    → Final DOCX
```

Корпусная валидация реиспользует ту же цепочку, подставляя passthrough вместо LLM.

---

## 3. Критические находки (P0)

### P0-1. Отсутствие subprocess timeout при `.doc` конверсии

**Файл:** `processing_runtime.py`, функция `_run_completed_process()` (~line 139)

`subprocess.run()` вызывается без параметра `timeout`. Malicious или corrupted `.doc` файл может вызвать бесконечное зависание LibreOffice или antiword, заблокировав worker thread навсегда.

**Impact:** Denial of service. Один зависший файл может заблокировать обработку для всех пользователей в однопоточном Streamlit deployment.

**Рекомендация:** Добавить `timeout=120` (или configurable) в `subprocess.run()`. Поймать `subprocess.TimeoutExpired` и переbrosить как `RuntimeError` с user-facing сообщением.

### P0-2. OLE2 magic bytes не уникальны для Word DOC

**Файл:** `processing_runtime.py`, `_detect_uploaded_document_format()` (~line 115)

Magic bytes `D0CF11E0A1B11AE1` — это OLE2 Compound Document signature, общая для `.doc`, `.xls`, `.ppt`, `.msg` и других форматов Microsoft. Файл `.xls` с корректными magic bytes будет классифицирован как `"doc"` и отправлен на конверсию, которая либо:
- Выдаст cryptic error от LibreOffice (не перехваченный специально)
- Будет молча сконвертирован в некорректный DOCX (antiword path)

**Impact:** Confusing user experience. Пользователь загружает Excel и получает "конверсия не удалась" вместо "формат не поддерживается".

**Рекомендация:** После OLE2 magic match, проверить extension. Если extension не `.doc`, вернуть `"unknown"` (или выделить `"ole2_unknown"`). Альтернативно — проверить наличие OLE2 stream `WordDocument` (python-olefile), но это дороже.

---

## 4. Серьёзные находки (P1)

### P1-1. Normalization failure не использует `fail_critical_fn`

**Файл:** `application_flow.py`, `_prepare_run_context_core()` (~line 166)

`normalize_uploaded_document()` вызывается без try/except. При ошибке (нет конвертера, файл corrupt) `RuntimeError` пробрасывается наверх без structured error reporting. Параметр `fail_critical_fn` (доступный в `prepare_run_context`) не вызывается для normalization failures.

**Impact:** Пользователь получает raw `RuntimeError` вместо structured error message в UI. Background processing path (`prepare_run_context_for_background`) может потерять ошибку без user notification.

**Рекомендация:**
```python
try:
    normalized_document = normalize_uploaded_document(...)
except RuntimeError as exc:
    if fail_critical_fn:
        fail_critical_fn("doc_conversion_failed", str(exc))
    raise
```

### P1-2. Token non-determinism для `.doc` файлов

**Файл:** `processing_runtime.py`, `freeze_uploaded_file()` (~line 264)

File token вычисляется из `normalized_document.content_bytes` (post-conversion). LibreOffice и antiword+pandoc могут производить разные DOCX bytes для одного и того же `.doc` на разных запусках (metadata timestamps, different XML serialization). Это означает, что один и тот же `.doc` файл может получить разные tokens при разных uploads.

**Impact:** Caching, deduplication, restart-store — всё привязано к token. Non-deterministic token для `.doc` означает, что completed source не будет найден при перезагрузке, если конвертер произвёл другой output.

**Рекомендация:** Для `.doc` файлов вычислять token из **original source bytes** (до конверсии), а не из converted bytes. Или хранить original hash как stable identifier.

### P1-3. soffice failure не cascade к antiword fallback

**Файл:** `processing_runtime.py`, `_convert_legacy_doc_to_docx()` (~line 215)

Если `soffice` найден через `shutil.which()`, но конверсия **fails** (crash, corrupt output, permission denied), `RuntimeError` из `_convert_legacy_doc_with_soffice` пробрасывается напрямую. Fallback на antiword+pandoc **не происходит**.

**Impact:** На машине с установленным, но неработающим LibreOffice (broken installation, profile lock) конверсия всегда будет падать, даже если antiword+pandoc работает.

**Рекомендация:**
```python
if soffice_path:
    try:
        return _convert_legacy_doc_with_soffice(...), "libreoffice"
    except RuntimeError:
        pass  # fall through to antiword
```

### P1-4. `run_lietaer_validation.py` — 2032 строки, mixed concerns

**Файл:** `tests/artifacts/real_document_pipeline/run_lietaer_validation.py`

Файл объединяет: progress tracking, subprocess orchestration, Word XML numbering inspection, centered paragraph matching, acceptance evaluation, artifact management, runtime event processing, main execution. Это монолит, крайне сложный для review, testing и maintenance.

**Impact:** High maintenance cost. Любое изменение в acceptance logic требует навигации через 2000 строк несвязанного кода. Bug surface area велика.

**Рекомендация:** Вынести в отдельные модули:
1. `repeat_orchestrator.py` — subprocess launch + aggregation
2. `acceptance_evaluator.py` — acceptance checks + classification
3. `report_builder.py` — report construction
4. `artifact_manager.py` — formatting diagnostics collection, event log, output DOCX

### P1-5. Inconsistent report key naming

**Файлы:** `real_document_validation_structural.py` vs `run_lietaer_validation.py`

- `structural.py`: `"runtime_config"` 
- `run_lietaer_validation.py`: `"runtime_configuration"`

Любой downstream consumer, читающий оба типа отчётов, должен обрабатывать оба ключа.

Дополнительно, Lietaer report дублирует runtime fields: `model`, `chunk_size`, `max_retries` присутствуют и at top level, и nested under `runtime_configuration.effective`. Расхождение при изменениях — latent risk.

**Рекомендация:** Унифицировать ключ (`runtime_config` или `runtime_configuration`). Убрать top-level дубликаты, оставить только nested.

### P1-6. Repeat report missing keys vs single-run report

**Файл:** `run_lietaer_validation.py`

Repeat report **не содержит** `formatting_diagnostics`, `signals`, `preparation` — ключи, присутствующие в single-run report. Downstream код, обращающийся к `report["formatting_diagnostics"]`, получит `KeyError` на repeat reports.

**Impact:** Runtime crash при анализе repeat reports, если consumer не проверяет наличие ключа.

**Рекомендация:** Либо добавить aggregated `formatting_diagnostics` в repeat report, либо задокументировать report schema contract и добавить `.get()` guards в consumers.

---

## 5. Замечания средней важности (P2)

### P2-1. Silent exception swallowing при загрузке formatting diagnostics

**Файлы:** `real_document_validation_structural.py` (~line 374), `run_lietaer_validation.py` (~line 1299)

```python
try:
    payload = json.loads(Path(artifact_path).read_text(encoding="utf-8"))
except Exception:
    continue
```

Bare `except Exception: continue` скрывает corrupt diagnostics files. Count может быть under-reported, вызывая false acceptance в structural validation.

**Рекомендация:** Логировать warning при skip, или как минимум считать skipped files.

### P2-2. `expected_acceptance_policy` — dead field

**Файлы:** `corpus_registry.toml`, `real_document_validation_profiles.py`

Поле `expected_acceptance_policy` объявлено в обоих `DocumentProfile` и `RunProfile`, заполняется из registry, но **нигде не читается и не enforced**. Acceptance evaluation hardcoded.

**Impact:** Misleading API surface. Contributor может думать, что смена policy в TOML влияет на поведение.

**Рекомендация:** Либо имплементировать policy-driven acceptance, либо удалить поле и добавить TODO.

### P2-3. `UploadedFileStub` дублируется в двух файлах

**Файлы:** `real_document_validation_structural.py` (~line 30), `run_lietaer_validation.py` (~line 76)

Почти идентичные реализации stub для uploaded file. DRY violation.

**Рекомендация:** Вынести в shared utility (например, `real_document_validation_utils.py`).

### P2-4. `normalize_semantic_output_docx()` — no-op wrapper

**Файл:** `formatting_transfer.py` (~line 614)

Функция возвращает `docx_bytes` unchanged. Pipeline всё ещё вызывает её для backward compatibility.

**Рекомендация:** Добавить deprecation comment с planned removal date, или убрать вызов из pipeline.

### P2-5. `_is_heading_only_markdown` дублируется

**Файлы:** `document_pipeline.py` (~line 184), `real_document_validation_structural.py` (~line 175)

`structural.py` реимпортирует или reimplements ту же проверку. Две копии логики — risk drift.

**Рекомендация:** Единственный source of truth в `document_pipeline.py`, импорт в `structural.py`.

### P2-6. `lru_cache` на `load_validation_registry` с unhashable-friendly but non-canonical paths

**Файл:** `real_document_validation_profiles.py` (~line 117)

`maxsize=1` кеширует только первый вызов. `Path("./corpus_registry.toml")` и `Path("corpus_registry.toml")` — разные ключи кеша. В тестах с параметризованными путями это вызовет cache misses.

**Рекомендация:** Канонизировать path через `Path(path).resolve()` перед `lru_cache`.

### P2-7. `bool` subclass of `int` не перехвачен в `_coerce_int`

**Файл:** `real_document_validation_profiles.py` (~line 254)

`isinstance(True, int)` возвращает `True`. TOML поле `min_paragraphs = true` пройдёт как `1`. Маловероятно в practice (TOML types explicit), но type-safety gap.

**Рекомендация:** Добавить `if isinstance(value, bool): raise ...` перед `isinstance(value, int)`.

### P2-8. `BytesIO` fallback для filename

**Файл:** `processing_runtime.py`, `freeze_uploaded_file()` (~line 266)

```python
filename = getattr(uploaded_file, "name", str(uploaded_file))
```

Если `uploaded_file` — `BytesIO` без `name`, `str(BytesIO())` → `"<_io.BytesIO object at 0x...>"`, что станет частью filename и token.

**Рекомендация:** Fallback на `"document.docx"` вместо `str(uploaded_file)`.

### P2-9. Non-integer `DOCXAI_REAL_DOCUMENT_REPEAT_COUNT_OVERRIDE` crashes

**Файл:** `run_lietaer_validation.py` (~line 1457)

```python
run_profile = replace(run_profile, repeat_count=max(1, int(repeat_count_override)))
```

Нет try/except. Malformed env var (`"abc"`) вызовет `ValueError` crash.

**Рекомендация:** Обернуть в try/except с fallback на profile default и warning.

### P2-10. Variable shadowing `failure_classification`

**Файл:** `run_lietaer_validation.py` (~line 537 vs ~line 573)

Loop variable `failure_classification` (line 537) и function-level result variable (line 573) используют одно имя. Не баг, но confusing.

**Рекомендация:** Переименовать одну из переменных (например, `run_failure_classification` для loop, `summary_failure_classification` для result).

---

## 6. Мелкие замечания и стиль (P3)

### P3-1. Unused import `qn` в `real_document_validation_structural.py`

`from docx.oxml.ns import qn` не используется.

### P3-2. `__import__()` inline в end-to-end тесте

**Файл:** `test_document_pipeline.py` (~line 1253)

```python
preserve_source_paragraph_properties=__import__("formatting_transfer").preserve_source_paragraph_properties,
```

Менее читаемо чем standard import at top. Рекомендуется обычный `from formatting_transfer import ...`.

### P3-3. `SessionState` class duplicated

**Файлы:** `test_processing_runtime.py` (~line 21) vs `conftest.py` (~line 22)

Идентичная реализация. Следует использовать fixture из conftest.

### P3-4. Redundant double-conditional для filename в `normalize_uploaded_document`

**Файл:** `processing_runtime.py` (~line 257)

```python
filename=normalized_filename if source_format == "docx" else filename
```

`normalized_filename` уже условно установлен на line 240. Двойная условность корректна, но добавляет cognitive load.

### P3-5. `output_heading_texts` computed twice

**Файл:** `run_lietaer_validation.py` (~line 1378, ~line 1397)

Два идентичных set comprehension по heading paragraphs. Можно консолидировать.

### P3-6. `image_mode` и `keep_all_image_variants` только для logging

**Файл:** `application_flow.py` (~line 294-295)

Параметры передаются в `prepare_run_context`, но используются только для log message (line 330-331), не для processing. Если это design intent — стоит задокументировать.

### P3-7. `SessionStateLike` protocol не декларирует attribute-style access

**Файл:** `application_flow.py` (~line 21-27)

Protocol определяет `__getitem__`/`__setitem__`, но код использует attribute access (`session_state.selected_source_token = ...`). Type checker может flag.

---

## 7. Покрытие тестами

### 7.1 `heading_only_output`

| Уровень | Тест | Вердикт |
|---------|------|---------|
| Pipeline rejection | `test_run_document_processing_rejects_heading_only_output_for_body_heavy_input` | ✅ Хорошо |
| Pipeline acceptance | `test_run_document_processing_accepts_heading_only_output_for_legitimate_heading_only_input` | ✅ Хорошо |
| Report classification | `test_classify_failure_detects_heading_only_output_from_block_rejection_event` | ✅ Хорошо |
| Repeat aggregation | `test_summarize_repeat_runs_detects_intermittent_failures` | ✅ Хорошо |
| **Multi-block partial failure** | — | ❌ Отсутствует |
| **Boundary condition `_input_has_body_text_signal`** | — | ❌ Отсутствует |
| **`structural.py` separate `_is_heading_only_markdown`** | — | ❌ Отсутствует |

### 7.2 Legacy `.doc` normalization

| Уровень | Тест | Вердикт |
|---------|------|---------|
| Runtime freeze | `test_freeze_uploaded_file_normalizes_legacy_doc_payload` | ✅ Properly mocked |
| Application flow | `test_prepare_run_context_normalizes_legacy_doc_before_validation` | ✅ Properly mocked |
| Document read | `test_read_uploaded_docx_bytes_normalizes_legacy_doc_upload` | ✅ Properly mocked |
| **Error path (no converter)** | — | ❌ Отсутствует на всех уровнях |
| **soffice → antiword fallback** | — | ❌ Backend selection not tested |
| **Corrupt .doc handling** | — | ❌ Отсутствует |

### 7.3 Misleading test

`test_build_uploaded_file_token_renames_zip_payloads_to_docx_extension` — название подразумевает тест `.doc` normalization, но bytes начинаются с `PK\x03\x04` (ZIP magic), поэтому format detection возвращает `"docx"`, и `.doc` conversion path **не тестируется**. Тест фактически проверяет filename renaming для DOCX с неправильным расширением.

### 7.4 Общие gaps

| Gap | Severity |
|-----|----------|
| No test: `generate_markdown_block` raises generic exception | Medium |
| No test: `_summarize_repeat_runs` with all runs failing | Medium |
| No test: `_summarize_repeat_runs` with zero runs | Medium |
| No test: empty processing event queue drain | Low |
| No test: `prepare_run_context` when `prepare_document_for_processing_fn` raises | Medium |
| No test: completely empty DOCX (no paragraphs) | Low |
| No test: DOCX with only images, no text | Low |
| Early pipeline tests don't use `_run_processing` helper — verbose boilerplate | Style |

---

## 8. Спецификация vs реализация

Сопоставление с `UNIVERSAL_REAL_DOCUMENT_VALIDATION_SPEC_2026-03-21.md`:

| Spec requirement | Implementation status |
|-----------------|----------------------|
| Generic registry-driven profiles | ✅ `corpus_registry.toml` + `profiles.py` |
| Deterministic extraction tier | ✅ `structural.py:evaluate_extraction_profile` |
| Deterministic structural passthrough tier | ✅ `structural.py:run_structural_passthrough_validation` |
| Runtime-resolution and override reporting | ✅ `profiles.py:resolve_runtime_resolution` |
| Repeat/soak execution | ✅ `run_lietaer_validation.py:_run_repeat_validation` |
| Second corpus document | ✅ `religion-wealth-core` in registry |
| `heading_only_output` regression | ✅ Three levels of coverage |
| Legacy `.doc` auto-conversion | ✅ `processing_runtime.py` |
| `religion-wealth-core` strict structural mode | ⏳ Intentionally tolerant (documented) |
| `expected_acceptance_policy` enforcement | ❌ Field exists but never enforced |
| Corpus promotion workflow | ⏳ Ongoing, not automated |

---

## 9. Итоговая матрица рисков

| ID | Finding | Severity | Likelihood | Impact | Effort to fix |
|----|---------|----------|------------|--------|---------------|
| P0-1 | No subprocess timeout | Critical | Medium | DoS | Low |
| P0-2 | OLE2 magic не уникален | Critical | Low | UX confusion + potential data corruption | Low |
| P1-1 | No structured error for normalization failure | High | Medium | Poor UX | Low |
| P1-2 | Token non-determinism для .doc | High | High | Broken caching/restart | Medium |
| P1-3 | No soffice → antiword cascade | High | Low | Blocked conversion | Low |
| P1-4 | Monolith runner 2032 LOC | High | — | Maintenance cost | High |
| P1-5 | Inconsistent report keys | High | Medium | Consumer breakage | Low |
| P1-6 | Missing keys in repeat report | High | Medium | KeyError crash | Low |
| P2-1 | Silent diagnostics skip | Medium | Low | False acceptance | Low |
| P2-2 | Dead `expected_acceptance_policy` | Medium | — | API confusion | Low |
| P2-5 | Duplicated `_is_heading_only_markdown` | Medium | Low | Logic drift | Low |
| P2-8 | BytesIO str fallback for filename | Medium | Low | Bad tokens | Low |
| P2-9 | Crash on non-integer env var | Medium | Low | Process crash | Low |

---

## 10. Рекомендации

### Immediate (before merge / next sprint)

1. **Добавить `timeout=120` в `_run_completed_process`** — P0-1, минимальный diff
2. **Добавить extension check после OLE2 magic match** — P0-2, ~5 строк
3. **Обернуть `normalize_uploaded_document` в `_prepare_run_context_core` в try/except** с `fail_critical_fn` call — P1-1
4. **Вычислять token из original source bytes для `.doc`** — P1-2, или хранить original hash separately
5. **Унифицировать `runtime_config` / `runtime_configuration`** — P1-5, search-replace
6. **Добавить `.get()` guards для optional report keys** или документировать schema contract — P1-6

### Short-term (next 1-2 sprints)

7. **Добавить try/except cascade для soffice → antiword** — P1-3
8. **Добавить тесты для error paths**: no converter available, corrupt .doc, multi-block heading_only
9. **Переименовать `test_build_uploaded_file_token_renames_zip_payloads_to_docx_extension`** чтобы отражать реальное поведение
10. **Решить судьбу `expected_acceptance_policy`** — implement or remove — P2-2
11. **Консолидировать `UploadedFileStub`** в shared utility — P2-3
12. **Канонизировать path в `load_validation_registry`** перед кешированием — P2-6

### Medium-term

13. **Декомпозировать `run_lietaer_validation.py`** — P1-4, большой refactoring
14. **Добавить secondary OLE2 stream validation** (python-olefile) для robust format detection
15. **Переименовать `run_lietaer_validation.py`** — уже не single-document scope (handoff question #1)
16. **Убрать `normalize_semantic_output_docx` no-op** из pipeline chain — P2-4

---

*Ревью завершено. 450 passed, 5 skipped — тестовая база стабильна. Основные архитектурные решения sound, рекомендуемые изменения фокусируются на hardening (timeouts, error paths, format detection robustness) и cleanup (deduplication, report schema consistency).*
