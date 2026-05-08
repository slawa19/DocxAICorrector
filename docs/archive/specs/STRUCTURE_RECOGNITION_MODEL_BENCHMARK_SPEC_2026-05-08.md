# Спецификация: мини-проект для сравнения моделей распознавания структуры документа

Дата: 2026-05-08

## Цель

Сделать быстрый изолированный benchmark-проект для выбора лучшей модели распознавания структуры документа в контексте существующего пайплайна DocxAICorrector.

Benchmark должен отвечать на практический вопрос: какая модель лучше всего помогает пайплайну восстановить структуру реального документа перед главо-ориентированной обработкой, переводом и постобработкой.

Проект должен быть устроен по тому же принципу, что `benchmark_projects/translation_quality_benchmark/`: отдельная поддиректория, собственный config, prompts, artifacts, runner, summary и review pack. Production-пайплайн можно импортировать и вызывать как библиотеку, но нельзя менять его поведение, UI, дефолтные модели или основной `config.toml` в рамках MVP.

## Решение, Которое Должен Поддержать Benchmark

Benchmark должен дать данные для следующих решений:

1. Какая модель лучше всего классифицирует роли абзацев: `heading`, `body`, `toc_header`, `toc_entry`, `list`, `caption`, `epigraph`, `attribution`, `dedication`.
2. Какая модель даёт наиболее полезные границы глав и секций после применения `detect_document_segments(...)`.
3. Какая модель минимизирует риски текущего пайплайна: heading-only collapse, bullet-as-heading, TOC/body concat, потеря TOC, избыточные fallback-сегменты.
4. Какая модель имеет лучший баланс качества, стабильности, latency и стоимости.
5. Как ранжируются все модели из заранее зафиксированного benchmark candidate set при одинаковом production-equivalent pipeline path.

## Non-Goals

Не строить универсальную платформу разметки документов.

Не менять production prompt `prompts/structure_recognition_system.txt` в рамках MVP.

Не менять `config.toml`, Streamlit UI, основной пайплайн подготовки или corpus registry без отдельного утверждения.

Не добавлять ручную gold-разметку для всего корпуса как обязательное условие первого запуска.

Не подменять реальные pipeline-метрики только LLM-суждением. GPT-5.5 является судьёй качества, но deterministic checks и pipeline outcome остаются обязательной частью оценки.

Не использовать перевод как способ оценки структуры. Benchmark оценивает подготовку структуры до translation/model-processing phases.

## High-Level Approach

Создать отдельный мини-проект:

```text
benchmark_projects/structure_recognition_benchmark/
  run.sh
  benchmark_runner.py
  benchmark_config.toml
  prompts/
    structure_judge_rubric.txt
  artifacts/
    runs/
```

Benchmark выполняет один run следующим образом:

1. Загружает selected document profiles из `corpus_registry.toml`.
2. Нормализует и извлекает реальные документы через существующий extraction path проекта.
3. Выполняет deterministic repair/validation baseline проекта.
4. Для каждой модели-кандидата запускает тот же production pipeline распознавания структуры, что и основной продукт, меняя только модель и benchmark-scoped runtime overrides, явно разрешённые этой спецификацией.
5. Сохраняет исходный `StructureMap`, usage, latency и связанные pipeline artifacts production path.
6. Применяет результат через тот же production apply/validation/segment path.
7. Запускает `detect_document_segments(...)` и pipeline structural checks на результате production path.
8. Сохраняет все промежуточные artifacts.
9. Запускает GPT-5.5 как анонимизированного судью по compact structural review pack.
10. Делает итоговое сравнение по deterministic metrics, judge scores, pairwise wins, стоимости и latency.

Ключевой контракт MVP:

1. Benchmark не должен изобретать отдельную задачу классификации структуры для кандидатов.
2. Главный смысл benchmark-а - проверить, как текущий production pipeline ведёт себя на разных моделях в одинаковых условиях.
3. Если candidate path не использует тот же production prompt, parser, `StructureMap` assembly, `apply_structure_map(...)` и downstream structural checks, такой path считается debug-only и не может использоваться для финального ranking.
4. MVP intentionally scopes paid candidate execution to a fixed `openrouter` candidate set that must be compared in one common run by default, not in split historical stages.

## Runtime Boundary

Benchmark считается consumer-проектом.

Allowed:

1. Импортировать `docxaicorrector.validation.profiles.load_validation_registry`.
2. Импортировать extraction helpers из `docxaicorrector.processing.processing_runtime` и `docxaicorrector.document._document`.
3. Импортировать `repair_pdf_derived_structure(...)`.
4. Импортировать `validate_structure_quality(...)`.
5. Импортировать `build_paragraph_descriptors(...)`, `apply_structure_map(...)` и модели `ParagraphClassification` / `StructureMap`.
6. Импортировать `detect_document_segments(...)`.
7. Импортировать public или semi-public diagnostic helpers только для read-only snapshot generation, если они уже используются validation harness.
8. Читать `corpus_registry.toml` и source files из `tests/sources/`.
9. Писать benchmark-only artifacts под `benchmark_projects/structure_recognition_benchmark/artifacts/`.
10. Менять model selection и benchmark-scoped app config overrides для production structure-recognition path, если эти overrides явно перечислены в benchmark config и не меняют production defaults в репозитории.

Forbidden:

1. Менять production modules ради benchmark MVP, кроме узкой read-only или dependency-injection-friendly интеграции, без которой benchmark не может вызвать уже существующий production path как consumer.
2. Менять Streamlit UI.
3. Менять `config.toml` model defaults.
4. Менять `corpus_registry.toml` без отдельного approval.
5. Писать результаты benchmark в `.run/ui_results/` или смешивать их с пользовательскими output artifacts.
6. Подменять финальный candidate execution benchmark-local prompt-ом или hand-rolled JSON task-ом вместо production structure-recognition pipeline.

## Candidate Models

Для MVP использовать фиксированный candidate set, который должен тестироваться в одном общем прогоне через OpenRouter:

```toml
[[candidates]]
id = "claude-haiku-4-5"
label = "Claude Haiku 4.5"
provider = "openrouter"
model = "anthropic/claude-haiku-4.5"

[[candidates]]
id = "gemini-3-flash"
label = "Gemini 3 Flash"
provider = "openrouter"
model = "google/gemini-3-flash-preview"

[[candidates]]
id = "gemini-3-1-flash-lite"
label = "Gemini 3.1 Flash Lite"
provider = "openrouter"
model = "google/gemini-3.1-flash-lite-preview"

[[candidates]]
id = "deepseek-v4-pro"
label = "DeepSeek V4 Pro"
provider = "openrouter"
model = "deepseek/deepseek-v4-pro"

[[candidates]]
id = "grok-4-3"
label = "Grok 4.3"
provider = "openrouter"
model = "x-ai/grok-4.3"

[[candidates]]
id = "qwen3-next-80b-a3b-instruct"
label = "Qwen3 Next 80B A3B Instruct"
provider = "openrouter"
model = "qwen/qwen3-next-80b-a3b-instruct"

[[candidates]]
id = "llama-3-3-70b-instruct"
label = "Llama 3.3 70B Instruct"
provider = "openrouter"
model = "meta-llama/llama-3.3-70b-instruct"

[[candidates]]
id = "gpt-5-4-mini"
label = "GPT-5.4 Mini"
provider = "openrouter"
model = "openai/gpt-5.4-mini"
```

Exact OpenRouter model IDs must be verified against the live OpenRouter model catalog before the first run. If a requested model is unavailable or has a different ID, record that in `model_availability.json` and skip or replace it only with explicit approval.

MVP deliberately keeps the paid benchmark `openrouter-only` and uses the fixed candidate set above as the default comparison set for the first full run.

Контракт baseline и candidate execution:

1. Все candidate models в MVP запускаются через один и тот же production structure-recognition path с одинаковым prompt, parser, `StructureMap` assembly и downstream apply/validation/segment flow.
2. Допустимые различия между candidate runs: модель, provider/base URL, API credentials, benchmark-scoped timeout/retry limits, а также document selection и artifact output root.
3. Недопустимые различия для финального ranking: отдельный candidate prompt, отдельный JSON schema contract для модели, отдельная benchmark-local windowing strategy для model inference, отдельный post-processing path, отдельный `StructureMap` merge algorithm.
4. Benchmark-local prompt допускается только для judge rubric и human-review packaging, но не для candidate inference.
5. Один benchmark run по умолчанию должен включать весь фиксированный candidate set; selective reruns разрешены только как debug или narrow follow-up path и не должны подменять основной общий ranking.

## Judge Model

Судья: `openai/gpt-5.5` по умолчанию.

Env override:

```text
STRUCTURE_BENCHMARK_JUDGE_MODEL=openai/gpt-5.5
```

Judge для MVP также выполняется через OpenRouter-compatible path. Если доступен точный dated model ID, runner должен записать requested model и returned model в `manifest.json` и judge metadata. Судейский результат не считается валидным, если returned judge model пустой или не матчится по семейству requested model (`openai/gpt-5.5*`) без флага `judge_model_mismatch`.

## API Strategy

MVP использует OpenRouter для candidate models и judge, по аналогии с translation benchmark.

Environment variables:

```text
OPENROUTER_API_KEY=...
STRUCTURE_BENCHMARK_JUDGE_MODEL=openai/gpt-5.5
STRUCTURE_BENCHMARK_OPENROUTER_REFERER=DocxAICorrectorStructureBenchmark
STRUCTURE_BENCHMARK_OPENROUTER_TITLE=DocxAICorrector Structure Benchmark
```

Правила:

1. Candidate calls и judge calls требуют `OPENROUTER_API_KEY`.
2. Judge и candidates должны использовать один и тот же OpenRouter base URL contract, если benchmark config явно не вводит отдельный non-default override.
3. Перед paid calls runner должен выполнить model availability preflight по OpenRouter catalog.
4. Недоступные модели пропускаются, но не заменяются автоматически.
5. Если после preflight осталось меньше двух candidate models и не включён baseline-only mode, run должен abort до paid calls.
6. Все usage/cost данные сохраняются отдельно для candidate calls и judge calls.
7. Источник истины для стоимости в MVP - provider-returned `usage.cost` или эквивалентное поле response payload. Если стоимость конкретного вызова отсутствует, этот вызов помечается `cost_unknown`, а cost-based ranking для соответствующего candidate/profile pair становится provisional.

## Benchmark Config Shape

```toml
[benchmark]
judge_model = "openai/gpt-5.5"
openrouter_base_url = "https://openrouter.ai/api/v1"
openrouter_referer = "DocxAICorrectorStructureBenchmark"
openrouter_title = "DocxAICorrector Structure Benchmark"
judge_prompt_file = "benchmark_projects/structure_recognition_benchmark/prompts/structure_judge_rubric.txt"
profiles = ["end-times-pdf-core", "lietaer-pdf-first-20-benchmark", "mazzucato-audiobook-core"]
max_profiles = 3
max_paragraphs_per_profile = 450
review_max_windows_per_profile = 4
review_max_window_paragraphs = 180
review_overlap_paragraphs = 20
request_timeout_seconds = 90
max_retries = 3
judge_temperature = 0.1
min_confidence = "medium"
chunk_size = 6000
run_deterministic_repair = true
run_deterministic_validation = true
run_segment_detection = true
run_judge = true
candidate_execution_mode = "production_pipeline"
candidate_inference_parameters = "inherit_production_defaults"
production_windowing_mode = "inherit_production_defaults"

[[candidates]]
id = "claude-haiku-4-5"
label = "Claude Haiku 4.5"
provider = "openrouter"
model = "anthropic/claude-haiku-4.5"

[[candidates]]
id = "gemini-3-flash"
label = "Gemini 3 Flash"
provider = "openrouter"
model = "google/gemini-3-flash-preview"

[[candidates]]
id = "gemini-3-1-flash-lite"
label = "Gemini 3.1 Flash Lite"
provider = "openrouter"
model = "google/gemini-3.1-flash-lite-preview"

[[candidates]]
id = "deepseek-v4-pro"
label = "DeepSeek V4 Pro"
provider = "openrouter"
model = "deepseek/deepseek-v4-pro"

[[candidates]]
id = "grok-4-3"
label = "Grok 4.3"
provider = "openrouter"
model = "x-ai/grok-4.3"

[[candidates]]
id = "qwen3-next-80b-a3b-instruct"
label = "Qwen3 Next 80B A3B Instruct"
provider = "openrouter"
model = "qwen/qwen3-next-80b-a3b-instruct"

[[candidates]]
id = "llama-3-3-70b-instruct"
label = "Llama 3.3 70B Instruct"
provider = "openrouter"
model = "meta-llama/llama-3.3-70b-instruct"

[[candidates]]
id = "gpt-5-4-mini"
label = "GPT-5.4 Mini"
provider = "openrouter"
model = "openai/gpt-5.4-mini"
```

CLI overrides:

```text
--config
--profiles
--candidates
--max-profiles
--max-paragraphs-per-profile
--skip-judge
--baseline-only
--output-root
```

## Corpus Scope

Первый быстрый run должен использовать реальные документы, уже покрывающие разные структурные риски:

```text
end-times-pdf-core
lietaer-pdf-first-20-benchmark
mazzucato-audiobook-core
```

Причины выбора:

1. `end-times-pdf-core` проверяет PDF-derived structure, TOC, списки, theology domain, bullet/list repair, TOC/body boundary.
2. `lietaer-pdf-first-20-benchmark` проверяет короткий PDF benchmark slice с headings и PDF conversion.
3. `mazzucato-audiobook-core` проверяет длинный DOCX/book-like source с headings и audiobook/translation-oriented downstream context.

Дополнительные profiles для последующего расширения:

```text
lietaer-core
religion-wealth-core
```

MVP не должен silently включать все документы. Цель первого run - быстрое сравнение, а не полный regression suite.

## Input Extraction Method

Benchmark должен извлекать paragraphs через существующий pipeline-compatible path:

1. Resolve `DocumentProfile.source_path` через `load_validation_registry(...)`.
2. Прочитать исходные bytes документа.
3. Нормализовать через `processing_runtime.normalize_uploaded_document(...)`.
4. Извлечь paragraphs через `extract_document_content_with_normalization_reports(...)`.
5. Применить `repair_pdf_derived_structure(...)`, если config включает `run_deterministic_repair` или profile требует PDF conversion/repair behavior.
6. Запустить `validate_structure_quality(...)` на repaired paragraphs.
7. Сформировать compact paragraph descriptors через `build_paragraph_descriptors(...)`.
8. Сформировать deterministic benchmark windows только для artifacts, review packs и judge inputs.

Не использовать ad-hoc `python -c` и не строить structural snapshot вручную, если уже есть reusable project helpers.

Inference contract:

1. Candidate inference не должен идти по benchmark-local window descriptors.
2. Candidate inference должен выполняться через production structure-recognition path на том же paragraph set, который реально получит основной pipeline после extraction/repair.
3. Если для ускорения MVP используется `max_paragraphs_per_profile`, ограничение применяется до candidate run на уровне benchmark corpus slice, а не как замена production internal windowing.
4. Benchmark review windows существуют только для explainability и judge packaging; они не являются отдельным inference API contract.

## Windowing

Для быстрого MVP нельзя превращать review artifacts в full-document dump. В этой секции слово `window` относится только к benchmark review windows, а не к production inference windows.

Window selection должен быть deterministic:

1. Всегда включать начало документа с front matter/TOC, если оно есть.
2. Включать окно вокруг первого body heading после TOC.
3. Включать среднее окно с обычным body text и потенциальными subheadings/lists.
4. Включать окно ближе к концу, если `max_windows_per_profile >= 4`.
5. Сохранять соседний контекст `context_before_preview` / `context_after_preview`, уже присутствующий в descriptors.
6. Не дробить внутри локального TOC cluster, если cluster помещается в лимит.

Эти окна не управляют candidate inference. Они используются только для:

1. `inputs/<profile_id>/...` artifacts;
2. judge packs;
3. human review pack;
4. локального объяснения, где именно модели расходятся.

Default для MVP:

```text
review_max_window_paragraphs = 180
review_overlap_paragraphs = 20
review_max_windows_per_profile = 4
```

Для каждого окна сохранить:

```text
inputs/<profile_id>/<window_id>.descriptors.json
inputs/<profile_id>/<window_id>.source_outline.md
inputs/<profile_id>/<window_id>.metadata.json
```

## Candidate Inference Contract

Candidate inference должен использовать production structure-recognition contract, а не benchmark-local prompt.

Rules:

1. Runner должен вызывать тот же production entrypoint или тот же underlying production helper chain, который используется в основном приложении для structure recognition.
2. Candidate execution должен использовать production prompt и production response parsing utilities.
3. Candidate execution должен возвращать тот же тип результата, что и production path: `StructureMap` плюс usage/metadata, пригодные для последующего `apply_structure_map(...)`.
4. Если benchmark вынужден вызывать нижележащий helper chain вместо верхнего convenience entrypoint, он обязан сохранить production-equivalent behavior и зафиксировать это в manifest notes.
5. Любой hand-rolled candidate prompt допускается только как debug artifact и не участвует в ranking.
6. Benchmark не должен добавлять benchmark-local `temperature`, `top_p` или другие generation параметры поверх candidate inference, если они не являются частью текущего production structure-recognition path. В manifest нужно явно фиксировать, что candidate inference использовал `inherit_production_defaults`.

Benchmark-local descriptor JSON сохраняется только для review artifacts. Он не является публичным candidate API contract для финального benchmark run.

## Candidate Output Normalization

Runner должен быть строгим, но не хрупким:

1. Parse raw model output using existing production response text utilities where possible.
2. Reject non-JSON commentary unless JSON object/array can be safely extracted.
3. Normalize role aliases only if explicitly listed in the production-compatible normalization contract used by the benchmark.
4. For review-window diagnostics, drop classifications for paragraph indexes outside the reviewed slice.
5. Mark missing indexes as `missing_classification` only inside benchmark review slices that are explicitly declared as expected-covered.
6. Paragraphs outside selected benchmark review slices must remain `unreviewed_by_benchmark_window`, not `missing_classification`.
7. Mark invalid role/level/confidence as `schema_violation`.
8. Convert valid rows to `ParagraphClassification` and aggregate into `StructureMap`.
9. Save raw output, normalized JSON, parse diagnostics and usage.

Artifacts per candidate/profile:

```text
candidates/<profile_id>/<candidate_id>/raw/<window_id>.txt
candidates/<profile_id>/<candidate_id>/normalized/<window_id>.classifications.json
candidates/<profile_id>/<candidate_id>/metadata/<window_id>.json
candidates/<profile_id>/<candidate_id>/usage/<window_id>.json
candidates/<profile_id>/<candidate_id>/structure_map.json
candidates/<profile_id>/<candidate_id>/applied_summary.json
candidates/<profile_id>/<candidate_id>/segment_diagnostics.json
candidates/<profile_id>/<candidate_id>/pipeline_checks.json
```

## Pipeline Reuse Flow Per Candidate

For each profile and candidate:

1. Clone repaired baseline paragraphs so candidates cannot mutate shared state.
2. Run the production structure-recognition path for that profile/corpus slice and obtain the resulting `StructureMap`.
3. Apply via `apply_structure_map(paragraphs, structure_map, min_confidence=config.min_confidence)`.
4. Run `validate_structure_quality(...)` again on post-AI paragraphs.
5. Run `detect_document_segments(paragraphs, source_content_hash16=..., chunk_size=...)`.
6. Build compact preparation diagnostic snapshot with the same fields used by structural validation where possible.
7. Store before/after deltas against deterministic baseline.

This makes benchmark result directly meaningful for the project: a model is not scored only by how plausible its labels look, but by whether the existing pipeline produces safer segments and quality gates after applying those labels.

## Baselines

Benchmark should record one baseline and one rules anchor:

1. `deterministic_repair_only`: extraction + repair + validation + segments, no AI classification.
2. `profile_expected_thresholds`: expectations from `DocumentProfile`, such as `min_headings`, `require_toc_detected`, `require_no_bullet_headings`, `require_no_toc_body_concat`, `require_numbered_lists_preserved`.

Baselines are not all equal candidates. They are comparison anchors used in summary and recommendation logic.

Baseline semantics:

1. `deterministic_repair_only` is the no-AI anchor.
2. `profile_expected_thresholds` is not a runnable model baseline; it is a rules anchor used to interpret deterministic checks.
3. Все candidate models ранжируются друг против друга внутри одного и того же benchmark run; summary не должен вводить отдельный privileged baseline среди них.

## Deterministic Metrics

For every profile/candidate collect:

```json
{
  "paragraph_count": 0,
  "nonempty_paragraph_count": 0,
  "input_window_count": 0,
  "review_window_count": 0,
  "classified_count": 0,
  "missing_classification_count": 0,
  "schema_violation_count": 0,
  "ai_heading_count": 0,
  "ai_toc_header_count": 0,
  "ai_toc_entry_count": 0,
  "ai_list_count": 0,
  "ai_epigraph_count": 0,
  "ai_attribution_count": 0,
  "heading_count_after_apply": 0,
  "toc_header_count_after_apply": 0,
  "toc_entry_count_after_apply": 0,
  "segment_count": 0,
  "high_confidence_segment_count": 0,
  "medium_confidence_segment_count": 0,
  "low_confidence_segment_count": 0,
  "fallback_segment_count": 0,
  "toc_matched_count": 0,
  "readiness_status": "ready",
  "quality_gate_status": "pass",
  "cost_known": true,
  "structure_fingerprint": "..."
}
```

## Automated Checks

Candidate receives flags from deterministic checks:

1. `invalid_json_output`: output cannot be parsed.
2. `schema_violations`: invalid role, heading level or confidence.
3. `missing_classifications`: candidate did not classify required descriptors.
4. `heading_only_collapse`: too many body paragraphs promoted to headings.
5. `bullet_heading_violation`: isolated bullet/number marker classified as heading.
6. `toc_not_detected`: profile requires TOC but no TOC header/entries are detected.
7. `toc_body_concat_risk`: final TOC line appears merged/confused with first body heading or epigraph.
8. `list_loss_risk`: profile requires lists but list/numbering evidence disappears.
9. `segment_fallback_overuse`: too many low-confidence/fallback segments after AI.
10. `segment_under_split`: expected multi-chapter document collapses into too few segments.
11. `segment_over_split`: ordinary body paragraphs create excessive tiny segments.
12. `readiness_regression`: post-AI readiness is worse than deterministic baseline.
13. `cost_or_latency_outlier`: candidate is materially slower or more expensive than peers.

Threshold contract for MVP:

1. `missing_classifications` applies only inside benchmark review slices declared as fully covered by the benchmark window. It must not be computed against the whole profile unless the whole profile was intentionally reviewed.
2. `heading_only_collapse` is raised when `heading_count_after_apply / max(nonempty_paragraph_count, 1) >= 0.20` and the ratio is at least `2.5x` the deterministic baseline heading ratio.
3. `severe_heading_only_collapse` is raised when `heading_count_after_apply / max(nonempty_paragraph_count, 1) >= 0.30` or when `heading_count_after_apply >= 3x` deterministic baseline headings.
4. `bullet_heading_violation` is raised when at least one isolated bullet glyph or standalone numeric marker becomes heading; severity becomes severe at `>= 3` violations.
5. `toc_not_detected` is raised when `DocumentProfile.require_toc_detected` is true and `toc_header_count_after_apply + toc_entry_count_after_apply == 0`.
6. `toc_body_concat_risk` is raised when the structural validation/reporting path indicates TOC-body concatenation or when a profile requiring `require_no_toc_body_concat` ends with fewer than `2` TOC entries before the first detected body heading despite TOC-like evidence in the baseline.
7. `list_loss_risk` is raised when `DocumentProfile.require_numbered_lists_preserved` is true and post-AI numbered/list evidence falls below `80%` of deterministic baseline retained list markers.
8. `segment_fallback_overuse` is raised when `fallback_segment_count / max(segment_count, 1) > 0.34` and severe at `> 0.50`.
9. `segment_under_split` is raised when `DocumentProfile.min_headings >= 3` and `segment_count < max(2, floor(min_headings * 0.5))`.
10. `segment_over_split` is raised when `segment_count > max(deterministic_baseline_segment_count * 2, deterministic_baseline_segment_count + 8)`.
11. `readiness_regression` is raised when deterministic baseline readiness is `ready` or expected-pass, but post-AI readiness becomes non-ready, blocked, warning, or fails profile structural expectations.
12. `cost_or_latency_outlier` is raised when candidate median latency is `>= 1.75x` peer median or candidate total cost is `>= 1.75x` peer median for the same completed profile set. If cost is unknown for one or more peers, the cost branch is skipped and the flag may be raised on latency only.
13. Every threshold above must be implemented as a pure deterministic function and covered by unit tests.

Hard failures excluded from judge:

1. invalid JSON for all windows of a profile;
2. no successful classifications;
3. candidate call failure for the profile;
4. heading-only collapse severe enough to make segment detection meaningless.

Ranking behavior for hard failures and partial judge coverage:

1. Hard-failed profile/candidate pairs remain in artifacts and summary; they are not silently dropped.
2. Judge scoring for a hard-failed profile/candidate pair is recorded as `not_judged`, not coerced to an invented natural-language verdict.
3. `average_judge_weighted_score` is averaged over successfully judged profile/candidate pairs only.
4. `pairwise_win_rate` is averaged over completed pairwise comparisons only.
5. If a candidate has fewer than `50%` of selected profiles successfully judged, the candidate cannot receive `best_structure_quality` or `best_price_quality`; minimum category is `needs_more_validation` unless deterministic results already force `not_recommended`.
6. If all selected profiles hard-fail for a candidate, `final_score = 0` and recommendation is `not_recommended`.

## GPT-5.5 Judge Inputs

Judge must not receive raw full documents by default. It receives compact, anonymized review packs per profile/window/candidate.

For each profile, build candidate review pack:

```text
PROFILE: end-times-pdf-core
WINDOW: toc_and_body_start

SOURCE PARAGRAPH OUTLINE:
001 | len=8 | style=Title | text="Contents"
002 | len=34 | text="Chapter 1 ........ 3"
...

CANDIDATE_X CLASSIFICATIONS:
001 | toc_header | level=null | confidence=high
002 | toc_entry | level=null | confidence=high
...

PIPELINE OUTCOME:
- headings_after_apply: 42
- toc_entries_after_apply: 13
- segment_count: 12
- fallback_segment_count: 0
- readiness_status: ready
- automated_flags: []
```

Judge prompt должен просить оценить не красоту объяснения, а практическое качество структуры для downstream pipeline.

## Judge Rubric

GPT-5.5 оценивает каждого кандидата по шкале 0-100 с весами:

| Criterion | Weight | Meaning |
|---|---:|---|
| Heading boundary accuracy | 18 | Правильно ли найдены главы, части, секции и реальные подзаголовки |
| Body preservation | 14 | Не превращает ли модель обычные абзацы, цитаты и служебный текст в headings |
| TOC handling | 14 | Отличает ли TOC header/entries от body и не смешивает TOC с первой главой |
| List and marker handling | 10 | Не делает ли bullet/number markers заголовками, сохраняет ли list semantics |
| Hierarchy and heading levels | 10 | Уровни заголовков логичны и не создают ложную глубину |
| Front matter roles | 8 | Корректно отличает dedication, epigraph, attribution, captions от headings/body |
| Segment usefulness | 12 | После классификации получаются полезные главы/секции для выбора пользователем |
| Pipeline safety | 8 | Не ухудшает readiness/quality gates и не создаёт downstream risks |
| Consistency across windows | 4 | Поведение стабильно на разных частях документа |
| Cost/latency practicality | 2 | Малый вес; качество структуры важнее стоимости, но outlier учитывается |

Judge output schema:

```json
{
  "candidate_scores": {
    "candidate_A": {
      "weighted_score": 0,
      "criterion_scores": {
        "heading_boundary_accuracy": 0,
        "body_preservation": 0,
        "toc_handling": 0,
        "list_and_marker_handling": 0,
        "hierarchy_and_heading_levels": 0,
        "front_matter_roles": 0,
        "segment_usefulness": 0,
        "pipeline_safety": 0,
        "consistency_across_windows": 0,
        "cost_latency_practicality": 0
      },
      "strengths": ["..."],
      "risks": ["..."],
      "editorial_verdict": "..."
    }
  }
}
```

## Pairwise Judging

После rubric scoring GPT-5.5 должен сделать попарные сравнения на одном и том же profile/window pack.

Pairwise output:

```json
{
  "comparisons": [
    {
      "left": "candidate_A",
      "right": "candidate_B",
      "winner": "candidate_A",
      "margin": "clear",
      "reason": "Candidate A preserves TOC/body boundary and avoids false headings."
    }
  ]
}
```

Allowed `margin`: `tie`, `slight`, `clear`, `decisive`.

Tie gives `0.5` win credit to both candidates.

## Final Scoring Formula

Итоговый score не должен быть одной голой judge-оценкой. Рекомендуемая формула:

```text
final_score =
  0.55 * average_judge_weighted_score
  + 0.20 * pairwise_win_score
  + 0.15 * deterministic_pipeline_score
  + 0.05 * reliability_score
  + 0.05 * cost_latency_score
```

Где:

```text
pairwise_win_score = pairwise_win_rate * 100
reliability_score = 100 - hard_failure_rate * 100 - normalized_schema_violation_penalty
cost_latency_score = capped inverse rank by cost and median duration
```

Где:

```text
normalized_schema_violation_penalty = min(25, schema_violation_rate * 100)
hard_failure_rate = hard_failed_profiles / max(selected_profiles, 1)
```

Если `usage.cost` неизвестен для части completed candidate/profile pairs, `cost_latency_score` must degrade gracefully: use latency-only ordering for those pairs, mark the resulting score as provisional in summary, and never invent synthetic provider pricing.

`deterministic_pipeline_score` считается из checks:

```text
100
- 25 * severe_heading_only_collapse
- 20 * toc_not_detected_when_required
- 18 * bullet_heading_violation
- 18 * toc_body_concat_risk
- 15 * readiness_regression
- 12 * segment_under_split_or_over_split
- 10 * segment_fallback_overuse
- 8  * list_loss_risk
- 5  * minor_schema_or_missing_classification_rate_bucket
```

Score clamp: `0..100`.

## Recommendation Categories

Runner должен присваивать каждому кандидату категорию:

```text
best_structure_quality
best_price_quality
promising_with_risks
needs_more_validation
not_recommended
```

Rules:

1. `best_structure_quality`: highest final score, no severe structural flags, pairwise win rate >= 0.60.
2. `best_price_quality`: within 5 points of quality leader and materially cheaper/faster.
3. `promising_with_risks`: candidate shows strong upside but has material caveats in reliability, cost, or narrow corpus stability.
4. `needs_more_validation`: promising but has narrow corpus coverage or instability.
5. `not_recommended`: severe flags, poor judge score, low reliability, or worse than deterministic baseline.

Additional gating rules:

1. Candidate cannot be `best_structure_quality` if it triggers any severe structural flag on any completed profile.
2. Candidate cannot be `best_price_quality` if it is worse than `deterministic_repair_only` on deterministic pipeline score for any profile with `structural_expected_result = "pass"`.
3. Candidate with incomplete judge coverage may still be ranked, but summary must mark the rank as provisional.

## Artifacts

Each run writes:

```text
benchmark_projects/structure_recognition_benchmark/artifacts/runs/<run_id>/
  manifest.json
  benchmark_config.snapshot.toml
  resolved_production_structure_prompt.snapshot.txt
  judge_prompt.snapshot.txt
  model_availability.json
  inputs/
  baselines/
  candidates/
  judging/
  summary.json
  summary.md
  findings_for_project_backlog.md
  human_review_pack/
    summary.md
    top_disagreements.md
    model_ranking_blinded.md
    model_mapping.json
```

Latest aliases:

```text
benchmark_projects/structure_recognition_benchmark/artifacts/latest_run.json
benchmark_projects/structure_recognition_benchmark/artifacts/latest_manifest.json
benchmark_projects/structure_recognition_benchmark/artifacts/latest_summary.json
benchmark_projects/structure_recognition_benchmark/artifacts/latest_summary.md
```

## Manifest Contract

`manifest.json` must include:

1. `run_id`, timestamps, status.
2. repo commit SHA and dirty-worktree flag.
3. config path and output root.
4. selected profile IDs.
5. source document paths and content hashes.
6. candidate list and available candidate list.
7. requested/returned models per candidate.
8. requested/returned judge model.
9. non-secret provider/base URL/referer/title values.
10. prompt snapshot paths.
10a. explicit note whether candidate execution used top-level production entrypoint or production-equivalent helper chain.
11. total candidate cost and total judge cost.
12. total candidate duration and judge duration.
13. hard failure counts.
14. notes and warnings.

## Summary Contract

`summary.json` must include:

```json
{
  "run_id": "...",
  "profiles": ["..."],
  "judge_model_requested": "openai/gpt-5.5",
  "judge_model_returned": ["..."],
  "candidate_count": 0,
  "profile_count": 0,
  "window_count": 0,
  "total_candidate_cost": 0.0,
  "total_judge_cost": 0.0,
  "rankings": [],
  "per_candidate": {},
  "per_profile": {},
  "baseline_comparison": {},
  "notes": []
}
```

Per-candidate summary:

```json
{
  "candidate_id": "gemini-3-flash",
  "label": "Gemini 3 Flash",
  "final_score": 0,
  "average_judge_weighted_score": 0,
  "pairwise_win_rate": 0.0,
  "deterministic_pipeline_score": 0,
  "reliability_score": 0,
  "cost_latency_score": 0,
  "recommendation": "best_structure_quality",
  "completed_profiles": 0,
  "failed_profiles": 0,
  "hard_failure_count": 0,
  "schema_violation_count": 0,
  "severe_flag_counts": {},
  "total_cost": 0.0,
  "average_latency_seconds": 0.0,
  "returned_models": [],
  "artifact_paths": []
}
```

`summary.md` должен быть компактным human-readable отчётом:

1. Run metadata.
2. Candidate ranking table.
3. Baseline comparison.
4. Per-profile winners and major failures.
5. Cost/latency table.
6. Overall recommendation and caveats.

## Human Review Pack

Human review pack должен позволять быстро понять спорные места без просмотра всех raw artifacts.

Files:

1. `summary.md`: короткий обзор run.
2. `top_disagreements.md`: окна, где judge увидел самые большие различия или decisive wins.
3. `model_ranking_blinded.md`: ranking без раскрытия model IDs.
4. `model_mapping.json`: mapping candidate labels только для финального unblinding.

`top_disagreements.md` должен показывать:

1. source outline для 10-30 релевантных paragraph descriptors;
2. классификации двух-трёх кандидатов;
3. deterministic flags;
4. краткое reasoning GPT-5.5.

## Findings Backlog

`findings_for_project_backlog.md` должен фиксировать только потенциальные улучшения production-пайплайна, найденные benchmark-ом.

Примеры:

1. Нужен prompt hardening для TOC/body boundary.
2. Нужен дополнительный deterministic guard против attribution-as-heading.
3. Нужны profile-specific expectations для segment counts.
4. Нужен UI warning, если selected model создаёт много low-confidence segments.

Этот файл не является разрешением на implementation. Любое изменение production code требует отдельной задачи.

## Implementation Phases

### Phase 1: Skeleton and Dry Run

1. Создать директорию `benchmark_projects/structure_recognition_benchmark/`.
2. Добавить `run.sh`, `benchmark_runner.py`, `benchmark_config.toml`, judge prompt и artifact scaffolding.
3. Реализовать config loading, run ID, artifact layout, snapshots, latest aliases.
4. Реализовать corpus profile loading и extraction до paragraph descriptors.
5. Реализовать baseline snapshots без candidate API calls.
6. Явно зафиксировать и artifact-нуть resolved production structure-recognition config/prompt, который затем будет использоваться и baseline, и candidates.

Exit criteria:

1. `run.sh --baseline-only --profiles end-times-pdf-core` создаёт artifacts.
2. `summary.md` показывает deterministic baseline и input windows.

### Phase 2: Candidate Calls

1. Реализовать OpenRouter availability preflight.
2. Реализовать candidate execution через production structure-recognition pipeline с model override, retries, timeout и usage capture.
3. Реализовать capture raw output / parse diagnostics без замены production parsing semantics.
4. Реализовать `apply_structure_map(...)`, validation, segments и checks.
5. Явно зафиксировать, что candidate inference parameters inherited from production defaults and benchmark review windows are not used as candidate inference inputs.

Exit criteria:

1. Один profile и два candidates успешно проходят end-to-end без judge.
2. Hard failures корректно artifacted и не ломают run.

### Phase 3: Judge and Ranking

1. Реализовать anonymized judge packs.
2. Реализовать GPT-5.5 rubric scoring.
3. Реализовать GPT-5.5 pairwise comparisons.
4. Реализовать final scoring, ranking, recommendation categories.
5. Реализовать human review pack.

Exit criteria:

1. Run на MVP profiles создаёт `summary.json`, `summary.md`, `human_review_pack/`.
2. Ranking объясним через judge scores, pairwise wins и deterministic flags для всего фиксированного candidate set.

### Phase 4: Validation and Hardening

1. Добавить unit tests для config parsing, output normalization, scoring formula.
2. Добавить tests с fake candidate outputs для severe flags.
3. Добавить no-network dry-run fixture.
4. Проверить canonical runtime через WSL project entrypoint.

Exit criteria:

1. Точечные tests проходят через canonical `bash scripts/test.sh ...`.
2. Benchmark dry-run не требует API keys.
3. Network run aborts cleanly before paid calls if candidate availability invalid.

## Test Strategy

Минимальные тесты:

```text
tests/test_structure_recognition_benchmark_config.py
tests/test_structure_recognition_benchmark_normalization.py
tests/test_structure_recognition_benchmark_scoring.py
```

Что покрыть:

1. TOML config parsing and CLI overrides.
2. Candidate model filtering.
3. JSON extraction from valid/invalid candidate output в production-compatible parsing path.
4. Role/level/confidence validation.
5. Missing classification handling.
6. Severe flag detection for bullet-as-heading and heading-only collapse.
7. Deterministic final score formula.
8. Recommendation category assignment.
9. Threshold contract for all severe and ranking-relevant flags.
10. Partial judging and hard-failure aggregation rules.
11. Provisional scoring behavior when `usage.cost` is absent.

Не запускать реальные paid API calls в unit tests.

## Canonical Run Commands

Agent-side direct run должен следовать repo runtime contract.

Из WSL project runtime:

```bash
bash benchmark_projects/structure_recognition_benchmark/run.sh --baseline-only --profiles end-times-pdf-core
bash benchmark_projects/structure_recognition_benchmark/run.sh --profiles end-times-pdf-core --candidates gemini-3-flash,gemini-3-1-flash-lite --skip-judge
bash benchmark_projects/structure_recognition_benchmark/run.sh --profiles end-times-pdf-core,lietaer-pdf-first-20-benchmark,mazzucato-audiobook-core
```

Первый user-visible paid run по умолчанию должен использовать весь фиксированный candidate set. Узкие `--candidates ...` reruns допустимы только для debugging или дополнительного расследования после основного общего прогона.

Для финальной pytest verification после implementation использовать только canonical test entrypoint:

```bash
bash scripts/test.sh tests/test_structure_recognition_benchmark_config.py -vv
bash scripts/test.sh tests/test_structure_recognition_benchmark_normalization.py -vv
bash scripts/test.sh tests/test_structure_recognition_benchmark_scoring.py -vv
```

## Acceptance Criteria

MVP считается готовым, когда:

1. Есть отдельный mini-project `benchmark_projects/structure_recognition_benchmark/`.
2. Production code, UI и main config не меняются для запуска benchmark.
3. Runner может выполнить baseline-only run без API keys.
4. Runner делает model availability preflight до paid calls.
5. Runner по умолчанию использует весь заранее зафиксированный OpenRouter candidate set.
6. Runner сохраняет raw, normalized, usage, checks, segments, judge и summary artifacts.
6a. Candidate ranking строится только по runs, выполненным через production structure-recognition pipeline path.
7. GPT-5.5 judge оценивает anonymized outputs по rubric и pairwise comparisons.
8. Итоговое сравнение учитывает judge score, pairwise win rate, deterministic pipeline score, reliability, cost и latency.
9. Summary явно показывает deterministic baseline, rules anchor, полный ranking всего candidate set и итоговые recommendation categories.
10. `findings_for_project_backlog.md` отделяет выводы benchmark от production implementation decisions.

