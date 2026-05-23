# Simple Reader-First MVP Spec

Date: 2026-05-21
Status: Proposed experiment; requires discovery gate before implementation; optimized for fastest validation, not full replacement

## Purpose

Проверить рабочую гипотезу: для обычного читательского результата может быть
эффективнее временно отказаться от сложного распознавания структуры и вместо
этого собрать простой переводческий pipeline с поздним reader cleanup pass.

Цель MVP - быстро получить сравнимый artifact на проблемной книге и ответить на
один вопрос:

```text
Даёт ли simple reader-first режим более читабельный Markdown/DOCX с меньшим
количеством page-furniture / OCR / layout-мусора, чем текущий structure-first
режим, без заметной потери основного текста?
```

Это не замена существующего structure-first pipeline. Это параллельный
экспериментальный режим для проверки продукта глазами читателя.

## Motivation

Текущая structure-first линия уже содержит много уровней: Stage 1 DocumentMap,
Stage 1.5 topology projection, Stage 2 anchored classification, structural
diagnostics, quality gates и backlog по новым сигналам. Последний full-book
benchmark может быть зелёным на acceptance уровне, но это не гарантирует, что
итоговая книга выглядит чисто для пользователя.

Основная проблема reader-facing результата часто выглядит проще, чем задача
полного structural authority:

- в текст попадают running headers / footers;
- остаются номера страниц и blank-page markers;
- часть PDF/OCR-мусора переводится как обычный текст;
- TOC, index, reference tail и сноски могут мешать continuous reading;
- попытки идеально распознать структуру создают длинный tuning loop.

Simple reader-first режим должен проверить альтернативу: не распознавать сложную
структуру, а сохранить базовую семантическую разметку и убрать очевидный мусор
после перевода.

## Core Hypothesis

Для reader-grade output достаточно:

1. безопасной deterministic pre-cleanup до перевода;
2. whole-document awareness pass, который возвращает компактный план, но не
   переписывает исходную книгу;
3. перевода крупными, устойчивыми chunks с базовой Markdown/DOCX разметкой;
4. whole-document cleanup planning после перевода, который видит всю книгу, но
   возвращает только компактные pattern/operation hints;
5. второго AI post-pass после перевода, который не форматирует документ заново,
   а предлагает только cleanup operations над блоками;
6. сохранения raw и cleaned artifacts для ручного сравнения.

The MVP should not translate or rewrite a full book in a single model response.
Whole-document context is useful for analysis and cleanup planning because those
stages return small outputs. Full-book translation as one response is not an MVP
target because output-size limits, truncation risk, retry cost, and alignment loss
make it a fragile proof path.

## Whole-Document Awareness Strategy

The reader-first experiment should test the likely root cause without creating a
new all-or-nothing generation path. The model should see the book as a whole only
when the output is compact and reviewable.

Recommended strategy:

```text
source document
  -> optional global read-only analysis plan          # compact JSON/text output
  -> translation in configured chunks                # not one whole-book output
  -> raw translated Markdown
  -> global cleanup planning over raw translation    # compact JSON/text output
  -> chunk/block cleanup operations                  # bounded edits only
```

### Why Not Whole-Book Translation In MVP

For Lietaer-like inputs, a whole-book call is dominated by output risk rather
than context-window risk. A model may accept the full source as input but still
fail to reliably generate the entire translated book as one response.

MVP must avoid:

- silent output truncation;
- skipped middle sections;
- repeated passages near long-generation boundaries;
- summary-like translation instead of faithful translation;
- one failed request invalidating the entire run;
- loss of source/target alignment needed for debugging.

### Translation Chunk Size Boundary

Translation chunk-size tuning is an external baseline experiment, not a required
MVP slice. The reader-cleanup MVP should consume whatever raw translated Markdown
the selected translation profile produces.

For this MVP, the only required boundary is:

```text
do not translate the entire book as one model output
do not make reader cleanup depend on a specific translation chunk_size
```

If a separate experiment selects a larger translation `chunk_size`, the cleanup
module should still work because it operates on final Markdown blocks rather than
translation job boundaries.

### Global Analysis Pass Before Translation

Optional in Slice 2+, but useful if the base translation run still shows
inconsistent terminology or repeated page-furniture translation.

The pass may read the full source text and return only a compact plan:

```json
{
  "book_title": "...",
  "style_notes": ["..."],
  "terminology": [{"source": "...", "target_hint": "..."}],
  "likely_repeated_noise_patterns": ["..."],
  "do_not_delete_examples": ["..."]
}
```

It must not rewrite or delete source text. Its output may be merged into existing
document context / glossary prompt mechanisms only after the base translation
run is measured.

### Global Cleanup Planning After Translation

Cleanup benefits more directly from whole-document visibility because repeated
noise is document-level evidence. The post-translation planning pass may read the
full raw translated Markdown and return a compact plan:

```json
{
  "repeated_noise_patterns": [
    {"pattern": "...", "reason": "running_header", "confidence": "high"}
  ],
  "candidate_block_ids": ["b_000142", "b_000381"],
  "warnings": []
}
```

The plan is advisory. Actual cleanup remains block-level, validated by `id` +
`text_hash`, and subject to safety limits.

## Non-Goals

- Не удалять существующий structure-first pipeline.
- Не менять текущие full-book acceptance gates.
- Не чинить Stage 1 / Stage 2 structure recognition.
- Не добавлять новые structure signals, topology rules или prompt schema для
  DocumentMap.
- Не делать новый универсальный Markdown structural postprocessor.
- Не восстанавливать настоящий Word TOC, footnote objects, page numbers или
  сложный book layout.
- Не обещать 1:1 сохранение исходного PDF/DOCX оформления.

## Desired Output Quality

MVP считается полезным, если cleaned artifact:

- сохраняет основной текст книги в исходном порядке;
- сохраняет базовые headings, paragraphs, lists и blockquotes, если они уже есть
  в Markdown;
- заметно уменьшает reader-visible мусор: колонтитулы, номера страниц,
  blank-page markers, повторяющиеся running headers, висячие footnote markers;
- не удаляет главы или смысловые блоки без явного report evidence;
- сохраняет raw artifact рядом с cleaned artifact для сравнения.

## Pre-Implementation Discovery Gate

Before writing `reader_cleanup.py`, prove that the simplified base path is
runnable for the selected target document.

Required discovery:

1. Run the selected document with `structure_recognition_mode = off` and reader
   cleanup disabled.
2. Confirm the run reaches final Markdown without segment-required,
   DocumentMap-required, or chapter-reassembly errors.
3. Save the raw Markdown artifact that will become the cleanup input.
4. Inspect whether the raw artifact has enough Markdown block boundaries for a
   block-level cleanup pass.

If the `off` path does not reach final Markdown, stop the reader-cleanup work and
fix only the minimal `off`-mode runtime issue first. Do not implement cleanup on
top of an unproven base path.

## Proposed Pipeline

```text
source PDF/DOCX
  -> existing extraction / preparation
  -> structure_recognition_mode = off
  -> deterministic safe pre-cleanup only
  -> optional global read-only context/noise plan
  -> existing translation block pipeline
  -> raw translated Markdown/DOCX artifacts
  -> optional global cleanup plan over full raw translated Markdown
  -> AI reader cleanup post-pass over translated blocks
  -> safety checks + cleanup report
  -> cleaned Markdown/DOCX artifacts
```

### Pre-Translation Cleanup

До перевода MVP должен использовать только безопасную deterministic-чистку.

Allowed:

- пустые / whitespace-only paragraphs;
- очевидные page numbers;
- явные PDF blank-page markers;
- технические placeholders и extraction artifacts.

Repeated running headers / footers are not a generic Markdown-level pre-cleanup
promise in MVP because page boundaries are usually unavailable after extraction.
They may be removed before translation only if the existing extraction layer
already exposes reliable page-boundary evidence for that exact source path.

Forbidden in MVP:

- AI cleanup source-текста до перевода;
- удаление всех footnotes / bibliography / index по умолчанию;
- распознавание chapter structure;
- merge/split heading fragments;
- TOC reconstruction;
- любые source-level операции, которые трудно откатить после удаления.

### Translation

Использовать существующий translation path как есть, но с отключённым structure
recognition:

```text
structure_recognition_mode = off
structure_recognition_enabled = false
```

Translation second pass можно оставить выключенным для первого MVP, чтобы не
смешивать literary polish с reader cleanup. Если нужен второй литературный проход,
он должен оставаться отдельной опцией и не заменять reader cleanup.

### Post-Translation AI Reader Cleanup

Второй проход должен быть AI, но ограниченный контрактом operations-only. Модель
не должна возвращать весь переписанный Markdown как единственный источник истины.

MVP cleanup is block-level first. Inline deletions are disabled for AI output in
Slice 1-2 because translated page-furniture strings may no longer exact-match the
source text and can be glued to semantic text. Inline cleanup may be added later
only for code-owned regex categories such as pure page numbers, explicit
blank-page markers, or exact repeated header lines.

Stable block identity contract:

- split the final translated Markdown into block records at cleanup time;
- `id` is the zero-padded block index in that exact raw cleanup input, for
  example `b_000142`;
- each block also stores `text_hash = sha256(normalized_text)[:16]`;
- every model operation must include both `id` and `text_hash`;
- the report stores `id`, `text_hash`, `raw_text_preview`, `char_count`, and
  block kind hints for review stability.

Recommended MVP model contract:

```json
{
  "delete_blocks": [
    {
      "id": "b_000142",
      "text_hash": "7f83b1657ff1fc53",
      "reason": "repeated_running_header",
      "confidence": "high"
    }
  ],
  "warnings": []
}
```

Any response that contains rewritten Markdown, unknown top-level fields, unknown
operation fields, duplicate block IDs, hash mismatches, or non-JSON prose must be
rejected or treated as no-op in advisory mode.

The code applies only allowed operations. The model is not allowed to:

- rewrite paragraphs for style;
- translate again;
- reorder blocks;
- change heading levels;
- create new headings;
- merge or split headings;
- reconstruct TOC;
- delete low-confidence semantic text.

## What Formatting Remains

The MVP preserves formatting only through existing Markdown semantics.

Expected to remain:

- headings represented as `#`, `##`, `###`;
- paragraphs and paragraph order;
- Markdown lists (`-`, `*`, `1.`) that already exist;
- blockquotes (`>`), if already present;
- basic emphasis if it survives the existing translation path.

Not expected in MVP:

- true Word TOC fields;
- source page numbers;
- original headers / footers;
- true Word footnote objects;
- exact PDF layout;
- complex tables or multi-column layout fidelity.

TOC policy should be explicit per profile:

- `keep_toc_as_text`: preserve TOC as ordinary translated text/list;
- `drop_toc_for_reading`: remove TOC in continuous reader/audio mode;
- no AI TOC repair in MVP.

Footnote policy should be conservative:

- remove only orphan markers by code-owned regex, such as standalone numeric
  marker paragraphs or dangling `[1]`-style marker lines;
- do not delete footnote bodies in MVP;
- remove bibliography / index / reference tail only in an explicit
  `drop_back_matter_for_reading` profile option.

For the first MVP, TOC policy is fixed to `keep_toc_as_text = true`. Dropping TOC
for audiobook or continuous-reading mode remains a later profile option.

## Known MVP Limitations

Current MVP limitations are acceptable unless they block the real-document
comparison goal:

- cleanup IDs, hashes, and raw sidecar are computed from the exact raw cleanup
  input, but cleaned output reconstruction may still be block-reconstructive
  rather than byte-preserving;
- first and last non-empty blocks may be treated as absolutely protected, even
  when a softer interpretation might allow certain high-confidence
  page-furniture heading deletions;
- footnote-body protection may remain intentionally narrow and deterministic; it
  is meant to prevent obvious false deletions without claiming full coverage of
  all footnote layouts;
- `reader_cleanup_drop_back_matter` may remain unsupported or warning-only in
  MVP and must not be treated as a proven cleanup-quality lever unless it is
  explicitly implemented and validated;
- a `50000` cleanup chunk profile is an optional experiment and does not, by
  itself, mean that the larger chunk size is a fully unlocked default contract.

## Fastest MVP On Existing Infrastructure

The fastest version should reuse existing pieces instead of adding new structure
machinery.

### Existing Infrastructure To Reuse

- UI / validation run-profile resolution in `src/docxaicorrector/validation/profiles.py`.
- Existing `structure_recognition_mode = off` path in preparation.
- Existing block translation execution.
- Existing translation second-pass model/client resolution patterns in
  `src/docxaicorrector/pipeline/block_execution.py`.
- Existing audiobook postprocess grouping pattern in
  `src/docxaicorrector/pipeline/late_phases.py`.
- Existing UI artifact writing path and `.run/ui_results/` conventions.
- Existing logging events and quality report retention patterns.

### Minimal New Config

Add profile/app config fields only if necessary:

```text
reader_cleanup_enabled: bool = false
reader_cleanup_model: str = ""
reader_cleanup_chunk_size: int = 30000
reader_cleanup_global_plan_enabled: bool = true
reader_cleanup_keep_toc: bool = true
reader_cleanup_drop_back_matter: bool = false
reader_cleanup_max_delete_block_ratio: float = 0.03
reader_cleanup_max_delete_char_ratio: float = 0.05
reader_cleanup_max_consecutive_deleted_blocks: int = 3
reader_cleanup_max_deleted_block_chars: int = 300
reader_cleanup_policy: "off" | "advisory" | "strict" = "advisory"
```

For the very first experiment, this can be hardcoded in one run profile instead
of fully wired into the UI.

### Minimal New Profile

Create a run profile similar to:

```toml
[run_profiles.ui-parity-translate-simple-reader-cleanup]
processing_operation = "translate"
structure_recognition_mode = "off"
structure_recognition_enabled = false
translation_second_pass_enabled = false
reader_cleanup_enabled = true
reader_cleanup_global_plan_enabled = true
reader_cleanup_policy = "advisory"
reader_cleanup_keep_toc = true
reader_cleanup_drop_back_matter = false
```

For MVP proof work, prefer a dedicated comparison-only variant of the same
profile rather than optimizing the first loop for acceptance green status:

```toml
[run_profiles.ui-parity-translate-simple-reader-cleanup-comparison-only]
comparison_only_validation = true
processing_operation = "translate"
structure_recognition_mode = "off"
structure_recognition_enabled = false
translation_second_pass_enabled = false
translation_output_quality_gate_policy = "advisory"
reader_cleanup_enabled = true
reader_cleanup_global_plan_enabled = true
reader_cleanup_policy = "advisory"
reader_cleanup_keep_toc = true
reader_cleanup_drop_back_matter = false
```

The comparison-only variant is the preferred MVP proof path when the goal is to
produce reviewable raw vs cleaned artifacts on a difficult real document. It is
not an acceptance-ready contract and must not be described as production proof.

If config schema work would slow down the experiment, use a narrow internal flag
in the validation harness first, then promote to profile config only after the
first artifact comparison is useful.

### Minimal New Module

Add one late-stage module, for example:

```text
src/docxaicorrector/pipeline/reader_cleanup.py
```

Recommended responsibilities:

- split final translated Markdown into stable block IDs;
- build cleanup prompt payloads;
- parse model JSON operations;
- apply allowed deletions;
- enforce safety limits;
- build cleanup report payload.

The block splitter must be deterministic for a given raw Markdown input. It does
not need cross-run stable IDs, but the report must include `text_hash` so a human
reviewer can detect when a later run shifted or changed a block.

Keep the module independent from structure recognition. It should not import
DocumentMap, topology projection, structural roles, or validators as authority.

### Minimal Integration Point

Integrate after final translated Markdown assembly and before final artifact
writing / DOCX conversion for the cleaned artifact.

The MVP should save both:

```text
<stem>.raw.result.md
<stem>.raw.result.docx
<stem>.cleaned.result.md
<stem>.cleaned.result.docx
<stem>.reader_cleanup_report.json
```

If writing two DOCX files is too much for the first slice, save raw Markdown,
cleaned Markdown, cleaned DOCX, and report.

Before wiring this into UI result events, verify how `ui_result_artifacts_saved`
and downstream tooling handle multiple artifact sets. If the existing event
supports only one stem group, log the cleaned artifact as the primary UI result
and include raw paths plus `reader_cleanup_report_path` as extra diagnostic
fields rather than silently replacing the established payload shape.

## Safety Checks

MVP must fail closed or warn loudly when cleanup is risky.

Suggested checks:

- deleted block ratio must be <= `reader_cleanup_max_delete_block_ratio` unless
  policy is explicitly relaxed;
- deleted character ratio must be <= `reader_cleanup_max_delete_char_ratio`;
- no more than `reader_cleanup_max_consecutive_deleted_blocks` may be deleted in
  one contiguous span;
- no block longer than `reader_cleanup_max_deleted_block_chars` may be deleted by
  the model in MVP;
- protected positions are never deleted: first non-empty block, last non-empty
  block, and Markdown headings unless explicitly classified as high-confidence
  page furniture;
- headings cannot be deleted unless the reason is `repeated_running_header` or
  `page_furniture_heading` with high confidence;
- no operation may reorder blocks;
- AI inline deletion operations are not accepted in MVP;
- every operation must pass `id` + `text_hash` validation against the raw cleanup
  input;
- low-confidence operations are ignored in strict mode and reported in advisory
  mode;
- cleaned text must not be empty and must preserve at least 90-95% of raw
  non-whitespace characters by default;
- every deletion must appear in the report with block id, reason, confidence, and
  before/after sample.

## Prompt Contract

The reader cleanup prompt should be intentionally narrow:

```text
You are cleaning a translated book Markdown for reading.
Do not translate, rewrite, polish, summarize, reorder, or reformat the book.
Return JSON cleanup operations only.
Delete only non-semantic PDF/OCR/layout noise: repeated running headers,
footers, page numbers, blank-page markers, orphaned footnote markers, and obvious
extraction artifacts.
Preserve chapters, headings, normal paragraphs, lists, quotes, footnote bodies,
bibliography, index, and TOC unless the profile explicitly allows dropping them.
If uncertain, keep the text and add a warning.
```

For MVP, avoid asking the model to decide broad structural questions. It is a
garbage-removal reviewer, not a structure recognizer.

Prompt instructions are not considered sufficient safety. Code-side schema
validation and operation filtering are required before any model-proposed cleanup
is applied.

## Chunking And Failure Policy

The cleanup pass must be cheaper and safer than translation, but it is still an
additional AI stage. MVP must log enough data to estimate cost and latency:

- raw block count and raw character count;
- cleanup chunk count;
- target characters per cleanup request;
- model selector and provider;
- per-chunk elapsed time;
- accepted, ignored, and rejected operation counts.

Chunking strategy:

- group contiguous Markdown blocks up to `reader_cleanup_chunk_size` characters;
- default cleanup chunk size for MVP is `30000` characters, with `50000` allowed
  only after the first run confirms stable schema-valid responses;
- preserve block IDs and text hashes across chunk boundaries;
- include limited neighboring block previews only for context, not as editable
  targets;
- never allow a chunk response to delete a block outside that chunk's editable ID
  set.

A `50000` cleanup chunk profile is an optional comparison experiment only. Its
presence in the registry does not mean that the repository considers `50000`
the default or fully unlocked contract path. Use it only after at least one
smaller-chunk cleanup run returns stable, schema-valid responses and produces
reviewable artifacts.

Partial failure policy:

- advisory mode: if a cleanup chunk fails schema validation or model execution,
  keep that chunk unchanged, add a warning, and continue;
- strict mode: fail the cleanup stage and preserve the raw result as the final
  artifact;
- any failed cleanup must log that the raw base result was preserved.

## Priority Rule: Product Value Over Local Green Tests

The primary goal of this MVP is not to maximize cleanup contract strictness or
test completeness in isolation.

The primary goal is to determine whether reader cleanup improves the
readability of a real translated document while keeping false deletions
acceptably low.

Priority order for this MVP:

1. Produce a real-document raw vs cleaned artifact pair that can be reviewed by
   a human.
2. Prevent dangerous semantic regressions and protected-block deletions.
3. Improve cleanup contract, logging, and regression coverage only insofar as
   they support the first two goals.

Green unit/integration tests alone do not count as proof that the MVP
succeeded. If the pipeline does not reach cleanup on the target real document,
the MVP validation question remains unanswered even if all targeted cleanup
tests pass.

## Anti-Overfitting Rule

Do not keep tightening cleanup heuristics, validation filters, or report detail
if those changes do not help answer the real-document comparison question.

A change is high-priority only if it does at least one of the following:

- helps cleanup execute on the target real document and produce reviewable
  artifacts;
- prevents a meaningful semantic regression or protected-block deletion;
- materially improves the interpretability of the real-document comparison
  result.

Changes that only improve local formal correctness, report richness, or
edge-case coverage without helping real-document validation should be treated as
secondary work.

For this MVP, the following are explicitly low-priority unless they block raw vs
cleaned artifact production or clearly correspond to reader-visible harm:

- tuning acceptance-only thresholds to make a comparison-only run look greener;
- expanding structural validation logic as the primary iteration loop;
- spending cycles on non-blocking `failed_checks` that do not change the human
  reading experience of the cleaned artifact.

## MVP Validation Plan

Use one problematic real document first. Do not use full-book as a tuning loop
unless a single milestone run is needed for artifact comparison.

### First Proof Document

The first reader-cleanup proof document for this MVP is fixed to the
non-contiguous Lietaer PDF region:

```text
document_profile_id = lietaer-pdf-chapter-region-core
source = tests/sources/Rethinking-money-chapter-region-pages-10-11-and-156-217.pdf
```

Reasoning:

- it is meaningfully harder than the small DOCX chapter sample for reader-facing
  cleanup evaluation;
- it includes both TOC-adjacent pages and later chapter-region pages where
  page-furniture, layout drift, and repeated noise are more likely to surface;
- it is still much cheaper and safer than using the full book as the default
  tuning loop.

## Validation Run Types

This MVP uses two distinct validation run types:

### Acceptance Validation Run

A normal validation run that keeps the standard document-level quality gate
behavior. This run answers whether the document is acceptable under the current
pipeline contract.

For the reader-cleanup MVP, this run is secondary evidence. It is allowed to
remain red while the team is still answering the reader-value question.

### Comparison-Only Validation Run

A dedicated comparison run whose purpose is to produce reviewable raw and
cleaned artifacts even if the translated output would not pass the normal
acceptance gate.

Rules for comparison-only runs:

- comparison-only runs must be clearly labeled as non-acceptance evidence;
- they must not be described as proving production readiness;
- they exist only to answer whether reader cleanup materially improves the same
  translated document output;
- they are the preferred proof path for the first MVP loop on
  `lietaer-pdf-chapter-region-core`;
- their final success criterion is `pipeline_result_and_artifacts`, not
  `acceptance_passed`;
- acceptance checks may still be recorded for diagnostics, but they are not the
  optimization target of this MVP loop;
- conclusions from a comparison-only run must still be checked against false
  deletions and protected-block safety.

If the normal acceptance run fails before cleanup executes, a comparison-only
path may be used to answer the raw-vs-cleaned artifact question without
claiming that the document is acceptance-ready.

## Quality Gate Interaction

If the normal translation quality gate fails before reader cleanup executes,
that run does not answer the cleanup usefulness question.

In that case, the team must choose one of two next steps:

1. fix the upstream blockers that prevent cleanup from running on the target
   document; or
2. use a clearly labeled comparison-only validation path to generate raw and
   cleaned artifacts for manual review.

Do not interpret a pre-cleanup quality-gate failure as evidence that reader
cleanup is ineffective. It only shows that the current run contract did not
reach the cleanup stage.

Do not respond to this situation by making acceptance checks themselves the main
development target. If cleanup already runs and produces artifacts, the next MVP
question is artifact quality, not acceptance greenness.

## AI Reader Verifier Development Step

Once the comparison-only run produces reviewable artifacts, the MVP should run a
separate development-only AI reader verifier.

Purpose:

- replace the first-pass manual comparison that would otherwise be done by a
  human reviewer on every iteration;
- assess whether cleaned output is more readable than raw output on the selected
  document slice;
- identify likely false deletions, major readability regressions, and remaining
  reader-visible noise;
- suggest only prompt, minimal-formatting, or deterministic-cleanup changes.

The verifier is not:

- a production acceptance gate;
- a replacement for standard repository validation;
- a reason to expand structure recognition or structural acceptance work;
- a universal AI judge of the entire book pipeline.

### Verifier Model Contract

For the first MVP verifier slice, the verifier target is fixed to the stronger
OpenRouter text selector:

```text
openrouter:google/gemini-3-flash-preview
```

Reasoning:

- it is stronger than the current repository default review/translation baseline;
- it is suitable for development-only comparison work;
- it keeps the verifier explicitly separate from the normal translation default,
  which may remain cost-optimized.

The verifier must use the existing provider-aware model resolution path and must
record all of the following separately:

- `verifier_requested_selector`
- `verifier_canonical_selector`
- `verifier_provider`
- `verifier_model_id`

The verifier must not silently fall back to:

- the repository default text model;
- the translation runtime model;
- the reader cleanup model;
- any bare OpenAI default.

If the exact verifier selector cannot be resolved or cannot be used at runtime,
the verifier must fail closed and emit an explicit non-success artifact state.

Allowed non-success reasons include:

- `verifier_disabled`
- `base_artifacts_missing`
- `model_selector_unconfigured`
- `model_resolution_failed`
- `provider_disabled`
- `api_key_missing`
- `model_unavailable`
- `execution_failed`

### Minimal Verifier Plumbing

The narrow MVP config shape is:

```text
reader_verifier_enabled: bool = false
reader_verifier_model: str = "openrouter:google/gemini-3-flash-preview"
reader_verifier_emit_summary: bool = true
```

For the first implementation slice, these may be wired only through the
comparison-only validation harness instead of broad UI/config plumbing.

### Execution Order And Non-Blocking Semantics

Required order:

1. comparison-only pipeline run finishes enough to save raw Markdown, cleaned
   Markdown, cleaned DOCX, and reader cleanup report;
2. source evidence payload is assembled;
3. verifier executes against that evidence;
4. verifier artifacts are written;
5. run report, summary, and latest manifest are updated with verifier metadata.

The verifier is non-blocking for comparison-only run completion semantics.

Rules:

- `acceptance_passed` remains diagnostic only;
- verifier verdict must not redefine acceptance status;
- if base comparison artifacts were produced, the comparison-only run remains
  `completed` even when verifier status is `not_run` or `failed`;
- verifier failure must never be reported as fake success;
- verifier absence must be visible in artifacts and summaries, not hidden.

### Evidence Input Contract

The verifier must work from evidence, not from acceptance counters.

For the first proof document `lietaer-pdf-chapter-region-core`, the default
review mode is:

```text
review the full selected slice
```

The chapter-region slice is intentionally bounded enough that the verifier should
prefer whole-slice evidence over tiny hand-curated snippets. Packetization is a
fallback only when the full evidence payload exceeds practical request limits.

The verifier input must be persisted as a machine-readable evidence packet:

```text
tests/artifacts/real_document_pipeline/runs/<run_id>/<artifact_prefix>_reader_quality_evidence.json
```

Required evidence packet contents:

- `run_id`
- `document_profile_id`
- `run_profile_id`
- `source_document_path`
- `evidence_mode = "full_selected_slice" | "packetized_selected_slice"`
- source extracted text for the reviewed slice, or explicit source packets when
  packetized mode is used;
- raw translated Markdown for the reviewed slice, or explicit raw packets when
  packetized mode is used;
- cleaned Markdown for the reviewed slice, or explicit cleaned packets when
  packetized mode is used;
- cleanup report summary, including accepted/ignored/rejected operations;
- deleted block previews with neighboring context when deletions exist;
- paths to the raw/cleaned artifacts used in review.

If packetized mode is required, packet selection must still preserve meaningful
document coverage. It must include, at minimum:

- TOC-adjacent region evidence;
- later body/chapter-region evidence;
- first and last narrative evidence within the selected slice;
- all deleted blocks plus local context;
- at least one unchanged normal-body sample for baseline comparison.

Tiny isolated snippets are not a valid verifier evidence substitute.

### Verifier Artifact Contract

The verifier must emit three run-scoped artifacts under:

```text
tests/artifacts/real_document_pipeline/runs/<run_id>/
```

Required files:

- `<artifact_prefix>_reader_quality_evidence.json`
- `<artifact_prefix>_reader_quality_review.json`
- `<artifact_prefix>_reader_quality_review.md`

The JSON review artifact is required even when the verifier does not run or
fails. In those cases it records an explicit `verifier_status` and
`verifier_reason` instead of conclusions.

These verifier artifacts must also be surfaced in repository-standard validation
outputs:

- include their paths in the run `report.json`;
- include their paths and top-level verifier fields in the run `summary.txt`;
- include their paths and top-level verifier fields in the latest manifest.

Verifier artifacts are validation evidence, not primary UI result artifacts. The
cleaned Markdown/DOCX remain the primary comparison output. Verifier review files
live in the validation run directory rather than in `.run/ui_results/`.

### Required Review JSON Contract

Minimum required review artifact shape:

```json
{
  "run_id": "...",
  "document_profile_id": "lietaer-pdf-chapter-region-core",
  "run_profile_id": "ui-parity-translate-simple-reader-cleanup-comparison-only",
  "review_mode": "development_only_non_acceptance",
  "verifier_requested_selector": "openrouter:google/gemini-3-flash-preview",
  "verifier_canonical_selector": "openrouter:google/gemini-3-flash-preview",
  "verifier_provider": "openrouter",
  "verifier_model_id": "google/gemini-3-flash-preview",
  "verifier_status": "completed|not_run|failed",
  "verifier_reason": "",
  "artifact_paths": {
    "source_evidence_json": "...",
    "raw_markdown": "...",
    "cleaned_markdown": "...",
    "cleaned_docx": "...",
    "reader_cleanup_report": "..."
  },
  "overall_verdict": "cleaned_better|raw_better|mixed|unclear",
  "reader_quality_score_raw": 0,
  "reader_quality_score_cleaned": 0,
  "confidence": "low|medium|high",
  "noise_removed": [],
  "possible_false_deletions": [],
  "readability_regressions": [],
  "recommended_next_changes": [
    {
      "change_type": "prompt|minimal_formatting|deterministic_cleanup",
      "recommendation": "...",
      "why": "..."
    }
  ],
  "summary_for_human": "...",
  "simple_user_summary": "...",
  "simple_user_risk_statement": "...",
  "simple_user_next_step": "..."
}
```

Rules:

- `overall_verdict` is a product-facing comparison result, not an acceptance
  result;
- `recommended_next_changes` are restricted to `prompt`,
  `minimal_formatting`, or `deterministic_cleanup`;
- if `verifier_status != "completed"`, then `overall_verdict` must be `unclear`
  and the summary fields must explain why the verifier produced no conclusion;
- no verifier output may recommend structure-recognition expansion,
  acceptance-threshold tuning as the primary next step, or broad validation
  framework rewrites.

### Markdown Summary Contract

The Markdown review artifact must be short, skimmable, and stable. Required
sections:

1. `Verdict`
2. `In Plain Words`
3. `Improvements Seen`
4. `Risks Seen`
5. `Recommended Next Changes`
6. `Verifier Metadata`

If the verifier did not run or failed, the Markdown summary must still be
written and must explicitly say:

- the verifier did not produce a review conclusion;
- why it did not run or failed;
- that raw/cleaned comparison artifacts were still preserved.

### User-Facing Interpretation Contract

The verifier exists to support later human explanation in simple language.
Therefore the verifier must produce summary text that is already easy to map into
plain user-facing conclusions.

Required user-facing semantics:

- avoid acceptance-first wording;
- avoid structural jargon unless it directly explains visible reading harm;
- separate `what improved`, `what is still risky`, and `what should change next`;
- state uncertainty explicitly when confidence is low;
- do not claim production readiness;
- do not claim semantic preservation unless the review evidence supports it.

Required simple-language verdict mapping:

- `cleaned_better`:
  `The cleaned version is easier to read than the raw translation. Most of the
  benefit comes from removing repeated reader-visible noise, and no major text
  loss was detected at current review confidence.`
- `raw_better`:
  `The cleanup pass removed or damaged meaningful text more than it improved
  readability. The raw version is safer to keep until cleanup rules are fixed.`
- `mixed`:
  `The cleanup pass improved some noisy sections, but it also introduced enough
  risk or regression that the result is not clearly better yet.`
- `unclear`:
  `The current run does not provide enough reliable verifier evidence to say
  whether cleaned output is better than raw output.`

The user-facing explanation derived from verifier artifacts should answer three
simple questions in order:

1. Is the cleaned result easier to read than the raw one?
2. Did cleanup appear to remove important text or only obvious noise?
3. What is the next narrow improvement category: `prompt`,
   `minimal_formatting`, or `deterministic_cleanup`?

### Comparison-Only Report And Summary Semantics

The main validation report should expose verifier evidence under a dedicated
section, for example `reader_verifier_evidence`, rather than mixing it into
acceptance checks.

The run summary should include, at minimum:

- `reader_verifier_status`
- `reader_verifier_reason`
- `reader_verifier_model_selector`
- `reader_verifier_model_id`
- `reader_verifier_overall_verdict`
- `reader_verifier_confidence`
- `reader_verifier_simple_user_summary`
- `reader_verifier_review_json`
- `reader_verifier_review_md`
- `reader_verifier_evidence_json`

The latest manifest should carry the same top-level verifier fields so later
automation can inspect the latest comparison-only review result without parsing
the full run report first.

### Recommended Validation Sequence

1. Run the selected proof document `lietaer-pdf-chapter-region-core` with
   `ui-parity-translate-simple-reader-cleanup-comparison-only`.
2. Verify that the run reached final artifacts and that raw vs cleaned Markdown
   can be reviewed.
3. Inspect cleanup report for false deletions and protected-block safety.
4. Persist the verifier evidence packet.
5. Run the AI reader verifier over source/raw/cleaned evidence.
6. Inspect verifier status, verdict, confidence, and simple-language summary.
7. Use the verifier output to guide only prompt, minimal-formatting, and
   deterministic-cleanup changes.
8. Keep at least one automated regression that proves protected blocks are not
   deleted: chapter heading sample, first/last narrative paragraph sample, normal
   list item sample, and footnote-body sample if present.
9. Decide whether the mode is worth implementing beyond MVP.

Minimal success criteria:

- at least 10 reader-visible noise instances are removed on the selected sample,
  or at least 70% of known sampled noise instances are removed if fewer than 10
  are present;
- false deletion count in the reviewed sample is <= 1 and there is no deletion of
  a protected block;
- no chapter-scale loss of text;
- no heading collapse worse than raw output;
- comparison-only run completes and saves reviewable raw/cleaned artifacts;
- verifier integration emits structured review artifacts on success and explicit
  `not_run` / `failed` artifacts on non-success;
- AI verifier or human review concludes that cleaned output is more readable than
  raw output, or at minimum identifies a clear next prompt/cleanup iteration;
- cleanup report is reviewable in under 5 minutes;
- cleaned artifact is more readable than raw artifact for the selected sample.

## Suggested Implementation Slices

### Slice 0: Off-Mode Discovery

- Run the target document with `structure_recognition_mode = off` and cleanup
  disabled.
- Confirm final Markdown is produced and artifacted.
- Record any downstream assumptions that still require segments, document maps,
  or chapter reassembly.
- Do not start Slice 1 until this discovery passes.

### Slice 1: Artifact-Only Prototype

- Add `reader_cleanup.py` with block splitting, fake/model-injected operations,
  operation application, and report generation.
- Add unit tests for stable block IDs, text hashes, operation application,
  schema rejection, protected-block behavior, and safety checks.
- No UI wiring.
- No profile schema expansion unless needed.

### Slice 2: AI Post-Pass Hook

- Add AI call using existing model/client resolution pattern.
- Use grouped chunks similar to audiobook postprocess.
- Enforce operations-only JSON schema and partial failure policy.
- Log cost/latency metrics for the cleanup stage.
- Save raw and cleaned Markdown artifacts plus cleanup report.
- Keep cleaned DOCX optional if artifact plumbing slows down the first test.

### Slice 3: Validation Profile

- Add one real-document comparison-only run profile with structure recognition
  off and cleanup on.
- Use `lietaer-pdf-chapter-region-core` as the first proof document.
- Ensure final status is based on artifact production, not acceptance green
  status.
- Record human-readable comparison notes in a short report.

### Slice 4: AI Reader Verifier

- Add a development-only verifier step after comparison-only artifact
  production.
- Feed persisted source/raw/cleaned evidence plus cleanup report into the fixed
  verifier model `openrouter:google/gemini-3-flash-preview`.
- Resolve and record `verifier_requested_selector`,
  `verifier_canonical_selector`, `verifier_provider`, and
  `verifier_model_id` through the existing provider-aware selector contract.
- Persist run-scoped evidence and review artifacts in the validation run
  directory.
- Surface verifier metadata into the run report, summary, and latest manifest.
- Keep the verifier non-blocking and explicitly labeled as non-acceptance
  evidence.
- Emit simple-language conclusion fields that can later be shown to the user
  without reinterpreting raw reviewer prose.

### Slice 5: UI Toggle Later

- Add UI checkbox only if Slice 1-4 show clear value.
- Suggested label: `Reader cleanup post-pass (experimental)`.

## Decision Gate

After MVP, choose one of three outcomes:

1. Promote reader-first cleanup as a UI experimental mode if the selected sample
   meets the minimal success criteria and the cleanup stage adds acceptable
   latency/cost for the document size.
2. Keep it only for audiobook / continuous reading outputs if it helps remove
   reader-visible noise but harms book-like DOCX formatting or TOC/back-matter
   expectations.
3. Drop it if false deletions, protected-block violations, formatting loss, or
   cleanup cost outweigh the readability gain.

Do not expand structure-recognition work based on this MVP unless the cleanup
report proves a specific upstream defect that cannot be safely handled late.

Do not treat acceptance-check tuning as a success path for this MVP. A greener
comparison-only report is not the goal unless it reflects a real reader-visible
improvement in the cleaned artifact.

## Resolved MVP Decisions

The first verifier-enabled MVP uses the following fixed decisions to avoid
ambiguity:

- TOC policy stays `keep_toc_as_text = true` for the reader-first MVP. TOC
  dropping remains a later explicit mode, not part of this verifier slice.
- Bibliography / index / reference-tail removal remains off by default and is a
  separate explicit future mode, not part of the first verifier slice.
- Cleanup safety thresholds stay locked at the current initial defaults (`3%`
  block ratio, `5%` char ratio, max 3 consecutive deleted blocks, max 300 chars
  per model-deleted block) for the first verifier slice. They must not be tuned
  merely to make the comparison-only report greener.
- Cleaned Markdown and cleaned DOCX are the primary comparison outputs. Raw
  Markdown is a required review/debug artifact. Raw DOCX is optional debug-only
  evidence and is not required for the first verifier slice.
- Verifier artifacts live in the validation run directory and are referenced by
  the report, summary, and latest manifest. They are not primary UI result
  artifacts.
- The verifier reviews the full selected chapter-region slice by default.
  Packetized evidence is only a fallback when full-slice review is too large for
  a practical request budget.
- If the verifier model cannot be resolved or executed, the run still preserves
  raw/cleaned comparison artifacts and emits explicit `not_run` or `failed`
  verifier review artifacts instead of silently substituting another model.
