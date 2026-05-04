# Translation Model Benchmark MVP Spec

## Goal

Run a fast, isolated benchmark to choose the best price-quality model for book translation, with Russian stylistic quality as the first target and a design that can later support other target languages.

The benchmark must use the existing document pipeline as a test harness, but it must not change production behavior, Streamlit UI, config defaults, or core pipeline code during this phase.

## Decision To Support

The benchmark should answer these questions:

1. Which candidate model produces the strongest Russian book-style translation for the selected corpus fragments?
2. Which model has the best practical price-quality ratio after accounting for edit risk?
3. Which top candidates are worth validating through direct provider APIs after the OpenRouter round?
4. Which model or models should later be added to the user-facing model list, after a separate approval step?
5. What project-level improvements were discovered by the test and should be specified separately before implementation?

## Non-Goals

Do not implement a full evaluation platform.

Do not add direct Anthropic, Google, xAI, or DeepSeek APIs in this phase.

Do not modify the main pipeline, UI model list, default model, or production config as part of the benchmark MVP.

Do not require human scoring for every candidate output.

Do not build a generic multi-language product workflow yet; only keep the benchmark data model target-language-aware.

## High-Level Approach

Create a small standalone benchmark project:

```text
benchmark_projects/translation_quality_benchmark/
  run.sh
  benchmark_runner.py
  benchmark_config.toml
  prompts/
    translation_to_ru.txt
  language_profiles/
    ru.toml
  artifacts/
    runs/
```

The benchmark will:

1. Load selected real-document profiles from `corpus_registry.toml`.
2. Use the existing project pipeline/preparation code to extract representative source fragments.
3. Send identical translation tasks to candidate models through OpenRouter.
4. Score each output with GPT-5.5 as the primary AI judge.
5. Run automated safety/structure checks.
6. Produce a compact human review pack with only final examples and judge reasoning.
7. Write all benchmark artifacts under `benchmark_projects/translation_quality_benchmark/artifacts/runs/<run_id>/`.

Benchmark-specific prompts and language profiles must live inside `benchmark_projects/translation_quality_benchmark/`, not in the main project `prompts/` tree. This keeps the benchmark isolated and avoids accidental production prompt changes during the MVP.

## Runtime Boundary

The benchmark is allowed to import and call project code, but it must be treated as a consumer of the project, not a production feature.

Allowed:

1. Import profile loading from `docxaicorrector.validation.profiles`.
2. Import document extraction/preparation helpers used by the existing pipeline.
3. Read `corpus_registry.toml`.
4. Read source documents referenced by corpus profiles.
5. Write benchmark-only artifacts.
6. Use environment variables for OpenRouter and judge configuration.

Forbidden in this phase:

1. Editing production pipeline modules.
2. Editing Streamlit UI.
3. Editing `config.toml` model options.
4. Changing `corpus_registry.toml` unless a new benchmark-only profile is explicitly approved.
5. Adding provider SDK abstractions to the main app.

## Candidate Models

Candidate definitions live in `benchmark_config.toml`, not in the main app config.

Example shape:

```toml
[benchmark]
target_language = "ru"
target_language_name = "Russian"
source_language = "en"
judge_model = "openai/gpt-5.5"
openrouter_base_url = "https://openrouter.ai/api/v1"
openrouter_referer = "DocxAICorrectorTranslationBenchmark"
openrouter_title = "DocxAICorrector Translation Benchmark"
translation_prompt_file = "benchmark_projects/translation_quality_benchmark/prompts/translation_to_ru.txt"
target_language_profile_file = "benchmark_projects/translation_quality_benchmark/language_profiles/ru.toml"

[[candidates]]
id = "claude-haiku-4-5"
label = "Claude Haiku 4.5"
provider = "openrouter"
model = "anthropic/claude-haiku-4.5"

[[candidates]]
id = "gemini-3-1-flash-lite"
label = "Gemini 3.1 Flash Lite"
provider = "openrouter"
model = "google/gemini-3.1-flash-lite"

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
```

Exact OpenRouter model IDs must be verified against the live OpenRouter model catalog before the first run. If a requested model is unavailable or has a different ID, record that in `model_availability.json` and skip or replace it only with explicit approval.

## API Strategy

Use OpenRouter for all candidate model calls in the MVP.

Use one OpenAI-compatible client pointed at:

```text
https://openrouter.ai/api/v1
```

Environment variables:

```text
OPENROUTER_API_KEY=...
TRANSLATION_BENCHMARK_JUDGE_MODEL=openai/gpt-5.5
TRANSLATION_BENCHMARK_OPENROUTER_REFERER=DocxAICorrectorTranslationBenchmark
TRANSLATION_BENCHMARK_OPENROUTER_TITLE=DocxAICorrector Translation Benchmark
```

Rules:

1. `OPENROUTER_API_KEY` is required.
2. The judge model may come from config, with `TRANSLATION_BENCHMARK_JUDGE_MODEL` as an override.
3. `openrouter_referer` and `openrouter_title` must be set either in config or through env overrides.
4. `manifest.json` must record the effective non-secret values used for judge model, referer, title, and base URL.

The benchmark must save usage data returned by OpenRouter:

```json
{
  "prompt_tokens": 0,
  "completion_tokens": 0,
  "total_tokens": 0,
  "reasoning_tokens": 0,
  "cached_tokens": 0,
  "cost": 0.0,
  "response_model": "...",
  "generation_id": "..."
}
```

For fair comparison, each call must log the requested model and the returned model. If they differ, the candidate result must be flagged.

### Model Availability Preflight

Before any translation or judge calls, the runner must query the live OpenRouter model catalog and validate every configured candidate ID.

Requirements:

1. Write the preflight result to `model_availability.json`.
2. Record requested model ID, matched catalog ID, availability status, and any mismatch reason.
3. Skip unavailable candidates automatically, but do not auto-replace them.
4. If fewer than 2 candidate models remain available after preflight, abort the run before translation begins.
5. This preflight happens before any paid benchmark requests so the run does not spend money on obviously invalid candidate IDs.

## Corpus Scope

Use the existing corpus registry.

First-pass profiles:

```text
mazzucato-audiobook-core
lietaer-core
```

Do not use `end-times-pdf-core` for this benchmark MVP.

The first run should use a small but varied fragment set rather than full documents.

Recommended MVP sampling:

1. 3 fragments from Mazzucato.
2. 3 fragments from Lietaer.
3. Each fragment should be around 1,500-3,500 source characters when possible.
4. Prefer fragments with complete paragraph boundaries.
5. Include at least one terminology-heavy fragment.
6. Include at least one rhetorically expressive or stylistically dense fragment.
7. Include at least one structurally non-trivial fragment with headings, lists, or adjacent formatting.

This gives approximately 6 fragments x 4 models = 24 translation calls, plus judge calls. That is enough for a fast decision-oriented first pass.

## Fragment Extraction Source And Method

The benchmark must extract source text from normalized source documents, not from translated pipeline output and not from AI structure-recognition results.

For the MVP, use this direct extraction path:

1. Resolve the source file from the selected `DocumentProfile`.
2. Normalize the uploaded document through `docxaicorrector.processing.processing_runtime.normalize_uploaded_document(...)`.
3. Call `extract_document_content_with_normalization_reports(...)` on the normalized document bytes.
4. Build candidate semantic groups with `build_semantic_blocks(paragraphs, max_chars=...)`.
5. Render selected fragment text with `build_document_text(selected_paragraphs)`.

Clarifications:

1. Do not run the full `processing.preparation` flow for fragment extraction.
2. Do not run AI structure recognition for the MVP fragment source path.
3. Use the extracted `ParagraphUnit.rendered_text` as the canonical source representation.
4. Preserve heading/list/paragraph boundaries exactly as represented by extracted paragraph rendering.
5. A thin benchmark-local wrapper is allowed to encapsulate this flow, but it must live inside the benchmark project and must not modify production helpers.

Fragment selection must be deterministic.

Recommended MVP selection algorithm:

1. Build semantic blocks from the extracted paragraphs.
2. Exclude image-only, table-only, or TOC-dominant blocks.
3. Prefer blocks whose rendered text falls within 1,500-3,500 source characters.
4. Select per-profile fragments from early, middle, and late document regions to avoid clustering in one section.
5. Keep paragraph boundaries intact; if a single block is too short, merge only adjacent blocks.
6. If a profile does not yield enough in-range fragments, widen the acceptable range to 1,000-4,500 characters before giving up.
7. If the target count still cannot be reached, write fewer fragments, record the reason in fragment metadata and the manifest, and continue the benchmark.

Each fragment metadata file should record why it was selected, its source profile, source character count, paragraph count, block indexes, and whether it was single-block or merged.

## Benchmark Modes

### MVP Mode: Fragment Translation

The first implementation should use fragment translation rather than full end-to-end document generation.

Purpose:

1. Compare model linguistic quality directly.
2. Keep runtime and cost low.
3. Avoid conflating translation quality with unrelated document-assembly failures.

Flow:

1. Extract text fragments from project-prepared document content.
2. Preserve minimal structure as Markdown.
3. Send the same fragment and prompt to every candidate model.
4. Score each output.
5. Generate summary and review pack.

### Optional Follow-Up Mode: End-To-End Spot Check

After MVP results, run only the top 1-2 models through a larger pipeline-oriented check.

This follow-up must be approved separately if it requires any production-code change.

## Translation Prompt

Use one fixed prompt for all candidates in the MVP.

The physical prompt file for the Russian MVP must live at:

```text
benchmark_projects/translation_quality_benchmark/prompts/translation_to_ru.txt
```

Do not reuse or edit the main project prompt registry in this phase.

The prompt must prioritize publishable Russian prose over literal word-for-word output, while preserving source meaning.

Prompt requirements:

1. Translate from English to Russian.
2. Produce polished book-quality nonfiction Russian.
3. Preserve argument, authorial voice, register, and rhetorical emphasis.
4. Avoid English syntactic calques.
5. Avoid bureaucratic filler and generic AI phrasing.
6. Preserve paragraph boundaries and Markdown structure.
7. Do not add commentary, explanations, prefaces, or metadata.
8. Keep terms consistent within the fragment.

The prompt should be target-language-aware, with the Russian language profile stored separately at:

```text
benchmark_projects/translation_quality_benchmark/language_profiles/ru.toml
```

Example shape:

```toml
name = "Russian"
quality_focus = "book-quality nonfiction prose"
avoid = [
  "literal English syntax",
  "bureaucratic filler",
  "unmotivated passive constructions",
  "excessive nominalization",
  "generic AI phrasing",
  "unstable terminology"
]
prefer = [
  "natural Russian clause order",
  "editorially polished rhythm",
  "clear causal links",
  "consistent domain terminology",
  "style that reads like professionally edited Russian"
]
```

For reproducibility, each run must snapshot both the resolved prompt text and the resolved target-language profile into the run artifact directory.

## Translation Request Execution

The MVP should prefer predictable execution over maximum throughput.

Requirements:

1. Translation calls run sequentially by default.
2. Retry on `429`, transient `5xx`, and transport timeouts with exponential backoff.
3. Save retry attempt counts, per-attempt errors, and final status in a per-output metadata artifact.
4. Requested model and returned model must always be recorded.
5. Output validation happens after the final successful response is received.

This benchmark is small enough that sequential execution is acceptable and reduces rate-limit noise during the MVP.

## AI Judge Strategy

GPT-5.5 is the primary judge for the MVP.

The judge must not see candidate model labels during scoring. It should receive anonymized candidate IDs such as `candidate_A`, `candidate_B`, and `candidate_C`.

Use two judge passes:

1. Per-candidate rubric scoring.
2. Pairwise ranking within each fragment.

This keeps the result more robust than a single absolute score.

For the expected MVP size of 4 candidates and 6 fragments, pairwise judging means 6 pairwise comparisons per fragment and 36 pairwise judge calls overall. This is acceptable for the MVP. If the candidate set grows beyond 5 models, pairwise cost increases quickly and the candidate list should be narrowed before the run or explicitly approved.

The benchmark must store both the requested judge model and the returned judge model in `manifest.json` and `summary.json`.

Judge-phase cost is expected to stay in the low single-digit USD range for the MVP fragment count. The runner should print the projected number of translation and judge calls before execution so cost is visible before the paid phase starts.

### Per-Candidate Rubric

Score each translation on a 100-point scale:

| Criterion | Weight |
|---|---:|
| Russian naturalness and idiomatic fluency | 20 |
| Semantic accuracy | 18 |
| Authorial voice and register | 14 |
| Freedom from English calques | 12 |
| Book-prose rhythm and readability | 10 |
| Terminology consistency | 10 |
| Discourse coherence across paragraphs | 6 |
| Structure and Markdown preservation | 5 |
| Low post-editing burden | 5 |

The judge output must be strict JSON:

```json
{
  "candidate_id": "candidate_A",
  "scores": {
    "russian_naturalness": 0,
    "semantic_accuracy": 0,
    "authorial_voice": 0,
    "anti_calque_quality": 0,
    "book_prose_rhythm": 0,
    "terminology_consistency": 0,
    "discourse_coherence": 0,
    "structure_preservation": 0,
    "post_editing_burden": 0
  },
  "weighted_total": 0,
  "verdict": "publishable_after_light_edit | usable_after_medium_edit | draft_only | unacceptable",
  "major_errors": [],
  "minor_errors": [],
  "best_features": [],
  "worst_features": [],
  "examples": [
    {
      "source_excerpt": "...",
      "translation_excerpt": "...",
      "comment": "..."
    }
  ]
}
```

### Pairwise Ranking

For each fragment, compare anonymized candidate outputs pairwise.

Judge output:

```json
{
  "fragment_id": "...",
  "comparisons": [
    {
      "left": "candidate_A",
      "right": "candidate_B",
      "winner": "candidate_A | candidate_B | tie",
      "margin": "slight | clear | decisive | tie",
      "reason": "..."
    }
  ]
}
```

Tie handling:

1. `tie` is allowed.
2. A tie counts as `0.5` pairwise win credit to each side.
3. Ties do not count toward decisive win count.

The final summary should include:

1. Average weighted rubric score.
2. Pairwise win rate.
3. Decisive win count.
4. Cost per fragment.
5. Cost per quality point.
6. Estimated cost per 300k-word book.
7. Editorial risk summary.

## Automated Checks

Keep automated checks small and practical.

Required checks:

1. Empty output.
2. Output too short or too long compared to source.
3. Untranslated English residue.
4. Repeated n-grams or obvious loops.
5. Paragraph count drift.
6. Markdown heading/list preservation.
7. Forbidden meta phrases such as `Here is the translation`.
8. Basic quote/bracket balance.

These checks should not decide the winner by themselves. They should flag risks for the judge summary and human spot-check.

### Hard Failure Versus Risk Flags

The benchmark must distinguish between a failed translation output and an output that is usable but risky.

Treat the output as `failed` for the fragment if any of the following is true:

1. The API call fails permanently after retries.
2. The final output is empty after trimming.
3. The final output is shorter than 60% of source character count or longer than 200% of source character count.
4. The output begins with or is dominated by forbidden wrapper/meta phrases such as `Here is the translation`.

Treat the output as `ok_with_flags` rather than `failed` if it only has softer issues such as untranslated residue, paragraph drift, repeated n-grams, heading/list preservation problems, or quote/bracket imbalance.

Failed outputs:

1. must still write metadata and automated check artifacts;
2. may omit `.ru.md` only if no usable text exists;
3. are excluded from judging for that fragment;
4. count against reliability and recommendation status in the final summary.

## Cost Scoring

For each candidate, compute:

```text
total_cost
avg_cost_per_fragment
cost_per_1k_source_chars
cost_per_1k_output_chars
cost_per_quality_point
estimated_cost_per_300k_word_book
```

`estimated_cost_per_300k_word_book` must be computed as a linear benchmark-only estimate, not as a production billing promise.

Method:

1. Compute observed `total_cost / total_source_chars` for each candidate across completed fragment calls.
2. Estimate source characters for a 300k-word book using the sampled corpus average source chars per word.
3. Multiply the observed cost-per-source-char by that estimated source character volume.
4. Include prompt overhead and retry overhead implicitly because they are already included in observed benchmark cost.
5. Label this value as an estimate that excludes future document-level effects such as chunk-boundary inefficiencies, provider price changes, and larger-book prompt-management overhead.

The final recommendation should not simply choose the cheapest model. It should classify candidates:

```text
best_quality
best_price_quality
budget_acceptable
not_recommended
```

## Human Spot-Check Pack

Human review is not part of primary scoring. It is a final sanity check.

Generate a compact review pack:

```text
artifacts/runs/<run_id>/human_review_pack/
  summary.md
  top_examples.md
  model_ranking_blinded.md
  model_mapping.json
```

`top_examples.md` should include:

1. 3 examples where the winner is clearly better.
2. 3 examples where the winner may be questionable.
3. 3 examples of serious errors across any model.
4. Cost-quality summary.
5. Judge rationale excerpts.

This is what the human checks after the benchmark, not every raw output.

## Artifacts

Each run writes:

```text
artifacts/runs/<run_id>/
  manifest.json
  benchmark_config.snapshot.toml
  translation_prompt.snapshot.txt
  target_language_profile.snapshot.toml
  model_availability.json
  fragments/
    <fragment_id>.source.md
    <fragment_id>.metadata.json
  translations/
    <fragment_id>/
      <candidate_id>.ru.md
      <candidate_id>.metadata.json
      <candidate_id>.usage.json
      <candidate_id>.automated_checks.json
  judging/
    <fragment_id>.rubric_scores.json
    <fragment_id>.pairwise.json
    <fragment_id>.judge_metadata.json
  summary.json
  summary.md
  findings_for_project_backlog.md
  human_review_pack/
```

`manifest.json` must include:

1. repo commit SHA if available;
2. run ID;
3. timestamp;
4. candidate list;
5. source profiles;
6. fragment IDs;
7. judge model;
8. OpenRouter base URL;
9. environment flags, excluding secrets;
10. Python version;
11. runtime platform details such as `uname` when available.

`summary.json` must also record:

1. requested judge model;
2. returned judge model or models observed during the run;
3. total judge cost;
4. total translation cost.

## Findings For Main Project

The benchmark may reveal improvement opportunities in the main project. Do not implement those automatically.

Write them to:

```text
artifacts/runs/<run_id>/findings_for_project_backlog.md
```

Each finding should use this format:

```text
## Finding: <short title>

Severity: critical | major | minor | cosmetic

Evidence:
<artifact paths and examples>

Impact:
<why it matters>

Suggested follow-up:
<separate spec or implementation idea>

Requires approval before implementation: yes
```

`summary.md` should emphasize `critical` and `major` findings first. `minor` and `cosmetic` findings may still be listed in the backlog artifact but should not dominate the benchmark conclusion.

Potential categories:

1. prompt improvements;
2. paragraph boundary preservation;
3. glossary handling;
4. model routing;
5. usage/cost accounting;
6. UI model selection;
7. output validation;
8. direct provider integration.

## CLI

MVP command:

```bash
bash benchmark_projects/translation_quality_benchmark/run.sh --config benchmark_projects/translation_quality_benchmark/benchmark_config.toml
```

Useful options:

```text
--target-language ru
--profiles mazzucato-audiobook-core,lietaer-core
--max-fragments 6
--skip-judge
--candidates claude-haiku-4-5,gemini-3-1-flash-lite
--output-root benchmark_projects/translation_quality_benchmark/artifacts/runs
```

`--skip-judge` is useful for debugging API calls and artifact generation.

## Implementation Plan

### Step 1: Skeleton

Add:

```text
benchmark_projects/translation_quality_benchmark/run.sh
benchmark_projects/translation_quality_benchmark/benchmark_runner.py
benchmark_projects/translation_quality_benchmark/benchmark_config.toml
benchmark_projects/translation_quality_benchmark/prompts/translation_to_ru.txt
benchmark_projects/translation_quality_benchmark/language_profiles/ru.toml
```

`run.sh` should follow the existing pattern from `benchmark_projects/pdf_candidate_benchmark/run.sh`:

1. cd to repo root;
2. activate WSL `.venv/bin/activate`;
3. set `PYTHONPATH`;
4. execute the runner.

`benchmark_runner.py` lives directly in `benchmark_projects/translation_quality_benchmark/`, matching the existing `pdf_candidate_benchmark` layout.

### Step 2: Config And Candidate Loading

Parse `benchmark_config.toml`.

Validate required environment:

```text
OPENROUTER_API_KEY
```

Fail clearly if missing.

Resolve prompt/profile inputs from benchmark-local files, snapshot them into the run directory, and validate that the configured candidate list has at least 2 entries.

### Step 3: Model Availability Preflight

Query the OpenRouter model catalog before any translation requests.

1. Validate configured candidate model IDs.
2. Write `model_availability.json`.
3. Skip unavailable candidates.
4. Abort early if fewer than 2 candidates remain.

### Step 4: Fragment Extraction

Load corpus profiles and extract text using existing project helpers.

Keep the first version simple:

1. normalize the source document;
2. extract `ParagraphUnit` content through `extract_document_content_with_normalization_reports(...)`;
3. build semantic blocks through `build_semantic_blocks(...)`;
4. choose deterministic fragments by position, structure, and length;
5. render source fragments through `build_document_text(...)`;
6. write source fragments and selection metadata to artifacts.

Avoid model calls during extraction.

Do not run AI structure recognition in this step.

### Step 5: Translation Calls

Call OpenRouter for each candidate/fragment pair.

Save raw response metadata, translated Markdown, usage, latency, retry history, requested model, returned model, and errors.

If a candidate fails on a fragment, continue the run and mark that output as failed.

Use sequential calls with retry and exponential backoff for rate-limit and transient transport errors.

### Step 6: Automated Checks

Run simple deterministic checks on each candidate output.

Save one JSON file per output.

Mark outputs as `failed` or `ok_with_flags` according to the hard-failure rules above.

### Step 7: GPT-5.5 Judging

For each fragment:

1. anonymize candidates;
2. run rubric scoring;
3. run pairwise scoring;
4. save strict JSON;
5. retry once if judge JSON is invalid;
6. record judge usage, requested model, returned model, and cost metadata.

Failed candidate outputs are excluded from fragment judging rather than being silently treated as low-quality translations.

### Step 8: Summary

Aggregate scores, pairwise wins, costs, and risk flags.

Write:

```text
summary.json
summary.md
human_review_pack/top_examples.md
findings_for_project_backlog.md
```

The summary must include total translation cost, total judge cost, pairwise tie handling, estimated cost per 300k-word book, and recommendation status per candidate.

## Acceptance Criteria

The MVP is complete when:

1. `run.sh --skip-judge` produces source fragments and candidate translation artifacts.
2. A full run with judge enabled produces `summary.md` and `summary.json`.
3. The run can continue if one candidate/model call fails.
4. All outputs are stored under benchmark artifacts only.
5. No production files are changed except the benchmark project and this spec.
6. The final summary includes a clear recommendation category for each model.
7. The final summary includes cost and quality, not quality alone.
8. The human review pack contains enough examples for selective manual verification.
9. Any suggested main-project optimizations are written as findings requiring approval.
10. The runner performs model-availability preflight before paid translation calls.
11. Hard translation failures are recorded consistently and excluded from judging.
12. `manifest.json` and `summary.json` record the effective judge model and runtime reproducibility details.
13. The runner handles missing env vars and per-fragment/provider errors gracefully.
14. MVP completion does not require benchmark-specific unit tests as a release gate, but the runner must remain deterministic for `--skip-judge` artifact generation and error handling.

## Recommendation Logic

Use this decision rule for the MVP summary:

1. If one model has the highest average score and at least a clear pairwise win rate advantage, mark it `best_quality`.
2. If another model is within 3 quality points but at least 30% cheaper, mark it `best_price_quality`.
3. If a model is cheap but requires medium/heavy editing, mark it `budget_acceptable` only if no serious semantic errors are detected.
4. If a model has repeated structural failures, serious semantic errors, or unstable output, mark it `not_recommended` even if cheap.

## Promotion Gate After Benchmark

Do not add winners to the user-facing model list automatically.

After reviewing `summary.md` and `human_review_pack/top_examples.md`, create a separate implementation plan for:

1. adding winner model IDs to `config.toml` if OpenRouter is accepted as a production provider;
2. adding direct provider APIs for the winner providers;
3. adding cost accounting to the main project if needed;
4. improving prompts or pipeline behavior if benchmark evidence supports it.

Each production change requires separate approval.
