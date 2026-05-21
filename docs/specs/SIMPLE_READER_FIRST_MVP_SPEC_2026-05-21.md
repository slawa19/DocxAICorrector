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

Partial failure policy:

- advisory mode: if a cleanup chunk fails schema validation or model execution,
  keep that chunk unchanged, add a warning, and continue;
- strict mode: fail the cleanup stage and preserve the raw result as the final
  artifact;
- any failed cleanup must log that the raw base result was preserved.

## MVP Validation Plan

Use one problematic real document first. Do not use full-book as a tuning loop
unless a single milestone run is needed for artifact comparison.

Recommended validation sequence:

1. Run existing structure-first profile and keep its latest Markdown/DOCX output.
2. Run `simple-reader-cleanup` profile on the same source.
3. Compare raw vs cleaned artifacts manually:
   - first 30 pages equivalent;
   - middle chapter region;
   - late book / back matter region;
   - known noisy page-furniture examples.
4. Inspect cleanup report for false deletions.
5. Run at least one automated regression that proves protected blocks are not
   deleted: chapter heading sample, first/last narrative paragraph sample, normal
   list item sample, and footnote-body sample if present.
6. Decide whether the mode is worth implementing beyond MVP.

Minimal success criteria:

- at least 10 reader-visible noise instances are removed on the selected sample,
  or at least 70% of known sampled noise instances are removed if fewer than 10
  are present;
- false deletion count in the reviewed sample is <= 1 and there is no deletion of
  a protected block;
- no chapter-scale loss of text;
- no heading collapse worse than raw output;
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

- Add one real-document run profile with structure recognition off and cleanup on.
- Run on one selected problem book.
- Record human-readable comparison notes in a short report.

### Slice 4: UI Toggle Later

- Add UI checkbox only if Slice 1-3 show clear value.
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

## Open Questions

- After MVP, should TOC be kept by default for DOCX and dropped by default for
  audiobook?
- Should bibliography/index removal be a separate explicit mode after the first
  keep-everything MVP?
- Are the initial safety thresholds (`3%` block ratio, `5%` char ratio, max 3
  consecutive deleted blocks, max 300 chars per model-deleted block) too strict
  or too permissive for the chosen corpus?
- Should raw and cleaned DOCX both be visible in UI, or should raw stay as a debug
  artifact only?
- Which one real document is the first acceptance sample for this experiment?
