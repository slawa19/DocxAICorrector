# Structure-Recognition → Reader-First Migration Plan

Date: 2026-05-29
Status: Active migration plan; structure-first tuning specs archived 2026-05-30

Связанные источники истины:

- `docs/specs/SIMPLE_READER_FIRST_MVP_SPEC_2026-05-21.md`
- `docs/specs/SIMPLE_READER_FIRST_MVP_REPAIR_PR_BACKLOG_2026-05-23.md`
- `docs/specs/PDF_TEXT_LAYER_SOURCE_IMPORT_PIVOT_SPEC_2026-06-01.md`
- `docs/archive/specs/STRUCTURE_RECOGNITION_PR_BACKLOG_2026-05-21.md` (тупиковая фаза)
- `docs/ARCHIVE_INDEX.md` (контракт архивации)

## 1. Цель и решение

Текущий structure-first пайплайн распознавания структуры (Stage 1 DocumentMap →
Stage 1.5 topology projection → Stage 2 anchored classification → structural
diagnostics → quality gates) признан тупиковым: он превратился в многоуровневый
набор эвристик, который дорого тюнить и который не гарантирует читабельный
reader-facing результат.

Решение:

1. Полностью исключить structure-first распознавание из продакшн-пайплайна.
2. Сделать основным путём **Simple Reader-First** (extraction → перевод большими
   chunks → AI reader cleanup post-pass).
3. Архивировать тупиковую фазу распознавания структуры вместе с документацией
   (без молчаливого удаления истории), а мёртвый код удалить из активного дерева.

Этот план НЕ предлагает чинить Stage 1/Stage 2; он переводит их в архив и
закрывает как активную поверхность разработки.

Важно: `structure-first` здесь означает именно AI-recognition/recovery pipeline
через DocumentMap/topology/anchored classification/reconciliation. Не весь
source-shape код автоматически является мёртвым: часть deterministic extraction,
layout cleanup, paragraph/relation normalization, image handoff и DOCX roundtrip
может остаться активной reader-first инфраструктурой после переименования и
развязки от structure-first терминологии.

## 2. Оценка готовности MVP

### Что уже готово

- **Slice 0–4 реализованы**: детерминированный block splitter + bounded
  operations, AI post-pass, comparison-only validation profile, AI reader
  verifier (`reader_cleanup_mvp/service.py`).
- **Runtime-интеграция уже есть**: `pipeline/late_phases.py`
  (`_run_reader_cleanup_postprocess` → `run_reader_cleanup`,
  `write_reader_cleanup_diagnostics`), гейтится `reader_cleanup_enabled` в
  `app_config`. Reader cleanup исполняется в основном пайплайне, а не только в
  валидации.
- **PR-G завершён по целевой границе**: validation больше не должна мутировать
  primary cleaned Markdown/DOCX; anchor repair остаётся runtime/diagnostic
  решением, а не validation-owned second repair pipeline.
- **Runtime anchor repair уже имеет частичный хук**: `late_phases` умеет читать
  `reader_cleanup_anchor_repair_enabled` и `reader_cleanup_anchor_targets`, но
  production source-of-targets и включение по умолчанию ещё не утверждены.

### Что ещё не готово

- **PR-H0/PR-H0a/PR-H0b/PR-H0c/PR-H0d/PR-H0e/PR-H0f/PR-H0g/PR-H0h завершены локально**:
  canonical
  small-overlap форма (`chunk_size=8000`, `3/3` read-only overlap,
  `global_plan_enabled=false`) зафиксирована как runtime/config/profile канон,
  inline markers закрыты, duplicate semantic heading targeting доказан, а
  side-heading operation choice переведён с unsafe `remove_inline_noise` на
  accepted `split_block` для proof examples. PR-H0d добавил bounded
  `extract_side_heading_and_reattach_body` и доказал его на single
  side-heading-island sentence interruptions. PR-H0e снизил broad unsafe
  `remove_inline_noise` proposals для semantic title deletion с `1` до `0`.
  PR-H0f доказал exact numeric-prefix cleanup для multi-word isolated semantic
  heading без удаления title text. PR-H0g доказал доступность same-block
  `join_fragmented_paragraph -> normalize_heading_boundary` runtime chain, но
  replay не дал effective fused-heading fix. PR-H0h добавил structured
  fused-heading targets и подтвердил safety, но repeat stability осталась
  quality-variable. Same-shape `gpt-5.4-mini` control завершился без failed
  chunks, но не конкурентен Anthropic (`remaining_issue_count=59`,
  `heading_fused_with_body=26`). **PR-H0 зафиксирован как reader-cleanup
  quality boundary, не как MVP exit proof.**
- Последний completed proof run
  `20260530T071434Z_968_Rethinking-money-chapter-region-pages-10-11-and-156-217`
  pipeline-level завершился и сохранил no-harm gates
  (`failed_chunk_count=0`, `accepted_delete_block_count=0`, false deletions /
  readability regressions empty, `page_furniture_inline=0`), но reader verifier
  упал: `reader_verifier_status=failed`,
  `reader_verifier_reason=execution_failed`,
  `reader_verifier_remaining_issue_missing_required_text`.
- Этот run **не является валидным MVP exit proof**. Deterministic pre-audit всё
  ещё сообщает `heading_fused_with_body=5` и `fragmented_paragraph=6`.
- Новый PR-H-exit runtime path для adjacent/split heading не доказан на real-doc:
  `heading_boundary_normalized_across_adjacent_block = 0`, то есть retained code
  path ни разу не применился в accepted operations.
- По May 26/30/June 1 evidence новые fused-heading micro-PRs больше не должны
  быть default next step. Остаточные PR-H defects считаются readable-draft /
  model-boundary limitations до свежего broad-class evidence. Verifier
  `execution_failed` по старому comparison-only run всё ещё запрещает MVP exit
  claim, но не блокирует старт PR-I как отдельного formatting workstream.
- **PR-PDF0 (Source Import Quality Gate)** активирован как новый
  highest-leverage source-quality slice перед расширением PR-I2. FineReader
  comparison показал, что текущий `writer_pdf_import` импортирует visual layout
  как document structure; поэтому сначала нужно измерить permissive
  text-layer-first импорт прямо в `ParagraphUnit`. PR-PDF0 probe на
  `Rethinking-money-chapter-region-pages-10-11-and-156-217.pdf` дал
  `decision=promising`, `visible_text_chars=95179`, `body_text_ratio=0.9882`,
  `heading_candidate_count=17`, `list_candidate_count=19`; следующий
  implementation PR — PR-PDF1 text-layer bridge. PR-PDF1a bridge proof уже
  показал viable generated-DOCX path (`140` paragraphs, `0` page-number-like
  paragraphs vs LibreOffice `336` / `1`), но выявил front-matter/TOC grouping и
  markdown-bold leakage через DOCX roundtrip. PR-PDF1 локально завершён как
  bridge, and PR-PDF3 promotes it to default PDF import: text-layer proof теперь даёт bounded TOC blocks (`124`
  paragraphs, `0` page-number-like paragraphs, `0` markdown emphasis markers)
  и generic blank-page notices удаляются до translation. PR-PDF2/OCR is deferred
  for the current MVP proof; partial plumbing remains behind explicit flags.
- **Formatting/image evidence по PR-PDF1:** text-layer bridge переносит
  структурные стили лучше текущего LibreOffice baseline (`16` heading
  paragraphs, `19` lists). Hybrid image handoff now inserts PDF image objects
  into the generated DOCX as normal inline Word images: proof artifact
  `.run/pdf_text_layer_quality/lietaer-chapter-region-format-image-comparison-hybrid-pr-j.json`
  shows `12` source PDF image objects -> `12` DOCX media / `12` DOCX drawings /
  `12` extracted image assets on the text-layer path. LibreOffice still has
  `12` media but `0` extracted assets in the current extractor.
- **PR-PDF3 readiness evidence:** two extra text-layer PDFs also favor the
  hybrid importer. `Rethinking-money-first-20-pages.pdf` gives `19` headings and
  `1` extracted image asset on the text-layer path versus LibreOffice `5`
  headings / `0` assets. The full Mariana PDF gives `32` headings, `379` lists,
  and `42` extracted image assets versus LibreOffice `27` headings, `363` lists,
  and `0` assets. Promotion still needs a fallback/quality gate because Mariana
  retains `10` page-number-like paragraphs on the text-layer path.
- **PR-PDF3 runtime switch:** PDF import now stays text-layer-first. Legacy
  `DOCXAI_PDF_TEXT_LAYER_IMPORT_ENABLED=0` no longer routes runtime PDF import
  to LibreOffice. Remaining LibreOffice PDF helper references are deletion
  cleanup debt, not product fallback policy.
- **PR-I (Formatting Preservation)** остаётся обязательным, но PR-I2 не должен
  расти до тех пор, пока PR-PDF0 не ответит, какие heading/bold/italic/list
  signals можно сохранить на source-import этапе.
- **PR-J (Image Handoff/Reinsertion)** text-layer bridge path is locally proven
  for embedded PDF image objects. Remaining image work is broader corpus/image
  quality validation, not reader cleanup.
- **Slice 5 / UI Toggle** не сделан: в UI есть чекбоксы для translation second
  pass и audiobook postprocess, но нет reader cleanup surface.
- **Reader cleanup config surface частично неполный**: `config.toml` уже содержит
  root-level `reader_cleanup_model`/`reader_verifier_model` и canonical
  small-overlap shape (`reader_cleanup_chunk_size=8000`, `3/3` overlap,
  `reader_cleanup_global_plan_enabled=false`), а `validation/profiles.py` уже
  читает reader-cleanup profile overrides. Всё ещё нет полноценного
  канонического блока/default surface для `reader_cleanup_default`, policy,
  safety budgets, TOC/back-matter policy, env и UI toggle.
- MVP exit criterion ещё не достигнут: нужен повторяемый `cleaned_better` без
  failed chunks / false deletions / readability regressions на основном proof-
  документе **плюс хотя бы один дополнительный реальный документ**.

### Ответ: после какой фазы MVP готов к интеграции

MVP готов стать основным пайплайном (а не comparison-only инструментом) **только
после разблокировки PR-H-exit/verifier proof, завершения PR-H до stable
visual-reader baseline, PR-I до formatting preservation contract, и MVP exit
criterion**; **PR-J обязательна дополнительно, если
PDF-origin картинки являются release-блокером** для целевого вывода.

Обоснование границы:

- **PR-H** сейчас заблокирован: последний completed proof имеет verifier
  `execution_failed`, remaining `heading_fused_with_body=5` /
  `fragmented_paragraph=6`, и новый adjacent-block heading path не применился
  (`heading_boundary_normalized_across_adjacent_block=0`). Gate не просто
  "добиться 0 failed chunks", а "получить валидный verifier proof, сохранить 0
  failed chunks/no-harm gates, и доказать или product-accept remaining
  reader-visible blockers".
- **PR-I** обязателен для замены structure-first как основного пайплайна: без
  сохранения bold/italic/заголовков/списков итоговый DOCX не дотянет до
  book-grade.
- **PR-J** — release gate по продуктовой политике: если картинки критичны, без
  неё замена неполна.
- **Slice 5 + флаги по умолчанию** — это собственно акт promotion в основной UI.

Короткая формула готовности:

```text
PR-H-exit verifier proof unblocked + PR-H stable visual baseline
  + PR-I formatting lineage + MVP exit criterion
  (proof doc + 1 дополнительный документ)
  [+ PR-J, если картинки — release-блокер]
  => reader-first готов заменить structure-first в продакшн-пайплайне и UI.
```

Verifier (Slice 4) и runtime-хук (`late_phases`) уже на месте, но verifier
execution must be healthy before any MVP exit claim. Остаточные gating-фазы —
PR-I lineage/preservation → optional PR-J → reader cleanup config/UI promotion →
Decision Gate, with the old PR-H-exit verifier issue retained as MVP-exit
evidence debt rather than the next cleanup micro-PR driver.

## 3. Current Codebase Inventory

Перед началом разработки этот inventory нужно держать как checklist. Главный
архитектурный риск: structure-first сейчас не изолирован в
`src/docxaicorrector/structure/`; он вплетён в preparation DTO, cache key,
relations/segments, UI application flow, validation profiles, config и tests.

| Area | Current state | Migration decision |
| --- | --- | --- |
| `src/docxaicorrector/structure/` | Stage 1/1.5/2 implementation: DocumentMap, recognition, topology, reconciliation, layout signals, validation. | Remove/archive after reader-first promotion and preparation decoupling. |
| `processing/preparation.py` | Direct imports from `structure.*`; runs validation, DocumentMap, topology, structure recognition; stores structure fields in `PreparedDocumentData`; cache key includes structure settings. | Add decoupling PR before deleting modules. Off-path must keep final Markdown path working without DocumentMap/StructureMap. |
| `core/models.py` | Contains `StructureRecognitionSummary`, `StructureMap`, `DocumentMap`, `DocumentTopologyProjection`, and structural hints on paragraph units. | Split AI-recognition models from still-needed source-shape metadata. Do not delete all structural fields in one PR. |
| `document/extraction.py` | `structure_recovery_enabled/mode` still controls deterministic source processing: inline-break normalization, heading promotion, front-matter title normalization, layout cleanup, PDF structure repair. | Decide what remains as reader-first source cleanup/layout hygiene, then rename/configure separately from structure-first. |
| `document/structure_authority.py` | Provides effective structural role / advisory phase helpers used by relations and structure-aware grouping. | Audit consumers before deletion; keep/rename only if reader-first chunking still needs neutral role authority. |
| `document/structure_repair.py` | PDF-derived source repair currently runs during extraction when structure recovery is enabled. | Decide whether this is reader-first source cleanup; if yes, move/rename under neutral source-cleanup owner. |
| `document/roles.py` | Structural role heuristics and role constants may still feed paragraph metadata. | Split source-shape hints from AI structure roles before deletion. |
| `document/boundary_review.py` | AI boundary review uses structure-recognition model role when enabled. | Remove or replace with reader-first/source-cleanup owner; do not leave dependency on structure model role. |
| `document/relations.py` | Imports DocumentMap and adds document-map TOC relations in `post_ai_final`. | Remove DocumentMap-dependent branch, keep deterministic relations if useful for reader-first chunking. |
| `document/segments.py` / `semantic_blocks.py` / `boundaries.py` | May use structure phases and hard boundaries for chunk assembly. | Audit and keep neutral chunking/selection logic; remove only DocumentMap/AI-structure authority branches. |
| `ui/_app.py` + `ui/structure_review_panel.py` | Structure review panel also owns selection/retry/context-policy helpers used by app flow. | Extract shared selection/retry helpers before deleting/replacing panel. |
| `ui/_ui.py` | Sidebar has translation/audiobook toggles but no reader cleanup toggle. | Add reader cleanup UI surface and app_config propagation. |
| `validation/profiles.py` | Run profiles already resolve reader cleanup settings, but still include structure-recognition fields and topology overrides. | Keep reader cleanup profile support; remove/compat structure fields after config migration. |
| `config.toml` / `core/config*.py` | Active `structure_recognition`, `structure_recovery`, `structure_validation`, and model role `structure_recognition`; root-level `reader_cleanup_model` / `reader_verifier_model` exist, but there is no full canonical reader-cleanup config block/default UI surface. | Complete reader cleanup config surface first; later migrate structure keys to deprecated no-op/renamed source-shape settings. |
| `corpus_registry.toml` | Mix of structure run profiles and reader-cleanup profiles; some profiles force `structure_recognition_mode = "always"`. | Freeze/archive structure profiles, keep/rename deterministic source/roundtrip tiers if still valuable. |
| `validation/structural.py` and real-document workflow docs | "structural" tier is partly deterministic passthrough/roundtrip, not purely AI structure recognition. | Do not delete blindly; rename/scope as source-shape or roundtrip validation if it remains useful. |
| `chapter_workflow/service.py` | Reads structure-recognition mode/min-confidence and may still own selected chapter workflows. | Audit after UI helper extraction; delete only if no reader-first selected-output workflow needs it. |
| Prompts/benchmarks/tests | Dedicated structure prompts, benchmark project, many `test_structure_*` tests. | Archive/remove after production code no longer imports them; update typecheck/static contract tests last. |

## 4. План замены пайплайна (Integration PRs)

Принцип: сначала сделать reader-first дефолтным и доказанным, и только потом
вырезать structure-first. Runtime/code decommission PR-D0+ не начинается раньше,
чем новый путь доказан на proof + дополнительном документе и UI.

### PR-M0. Plan Refresh + Inventory Lock

- Обновить repair backlog/status references: PR-H0 является текущим
  промежуточным slice; PR-H-exit остаётся следующим runtime proof slice, а
  PR-H1/PR-H2 не должны оставаться как актуальная формулировка текущего
  состояния.
- Зафиксировать текущий latest completed proof из repair backlog:
  `20260530T071434Z_968_...`, pipeline succeeded, no-harm gates green, verifier
  `execution_failed`, `heading_fused_with_body=5`, `fragmented_paragraph=6`,
  `heading_boundary_normalized_across_adjacent_block=0`.
- Зафиксировать explicit stop rule: decommission не начинается из-за одного
  pipeline-level success или `cleaned_better`; нужны completed verifier evidence
  и UI proof.

Выход: этот migration plan и repair backlog не противоречат друг другу.

### PR-H0. Canonical Small-Overlap + Shared Blind Spots

Завершённый промежуточный PR между model bake-off и PR-I formatting workstream.

Scope:

- Зафиксировать small-overlap как model-compatible reader cleanup форму, а не
  Anthropic-only workaround: `chunk_size=8000`, `overlap_blocks_before=3`,
  `overlap_blocks_after=3`, `global_plan_enabled=false`.
- Сохранить model selector отдельно от формы задачи: Gemini и Anthropic должны
  проходить через один chunk/overlap/JSON contract.
- Вынести общие blind spots из same-shape Anthropic/Gemini comparison в backlog:
  side-heading islands inside prose, duplicate semantic heading text, inline
  endnote/page markers, leading-dash continuation artifacts.
- Не расширять verifier boundary: verifier только оценивает/сигналит; cleanup
  operations остаются runtime-applied и safety-validated.

Non-goals:

- Не увеличивать chunk size в этом PR без отдельного repeated experiment.
- Не возвращать full global plan как default: он снова делает request shape
  bulk-like и хуже совместим с разными моделями.
- Не менять literary translation baseline.

Выход: config/runtime defaults и план согласованы с same-shape evidence;
small-overlap canon остаётся текущей reader-cleanup формой, Anthropic остаётся
cleanup leader, `gpt-5.4-mini` не принят как replacement, а дальнейшие
fused-heading micro-PRs остановлены как вероятное document polishing.

### PR-H0a. Inline Marker + Duplicate Heading Runtime Proof

Статус: завершён локально, не clean-checkout CI proof.

Proof artifact:
`.run/reader_cleanup_replay_experiments/20260530T133307Z_anthropic-small-overlap-pr-h0a-inline-marker-duplicate-boundary-proof/`

Результат:

- selector: `anthropic:claude-sonnet-4-6`;
- canonical shape: `chunk_size=8000`, `3/3` read-only overlap,
  `global_plan_enabled=false`;
- cleanup chunks: `15`, failed chunks: `0`;
- accepted cleanup operations: `49`, including `22` `remove_inline_noise`;
- verifier: `cleaned_better`, confidence `high`, raw `4.0` -> cleaned `6.0`;
- remaining issues: `17`;
- `noise_substring_not_found=0`, broad unsafe remove_inline_noise proposals `0`.

Closed by runtime proof:

- inline endnote/page markers, including `Однако в 1950-х годах 5 эта...`, now
  remove the marker without word-boundary collapse.

Implemented but not selected in the real replay:

- duplicate semantic heading contract for exact adjacent repeated phrases, e.g.
  `национальные валюты Национальные валюты`, is covered by unit tests but the
  proof run did not receive a model operation for that site. This is now an
  operation-selection/pre-audit targeting gap, not a runtime rejection.

PR-H0b/PR-H0c updates:

- PR-H0b proof:
  `20260530T155633Z_anthropic-small-overlap-pr-h0b-targeting-proof`, `15`
  chunks, `0` failed chunks, `52` accepted operations, verifier
  `cleaned_better` high confidence, `19` remaining issues. Duplicate semantic
  heading operation selection worked for `национальные валюты Национальные
  валюты`; side-heading islands still fell back to rejected
  `remove_inline_noise`.
- PR-H0c proof:
  `20260530T165518Z_anthropic-small-overlap-pr-h0c-side-heading-salience-proof`,
  `15` chunks, `0` failed chunks, `55` accepted operations, verifier
  `cleaned_better` high confidence, `20` remaining issues. Side-heading
  examples moved to accepted `split_block` operations and broad unsafe
  `remove_inline_noise` remained `0`; remaining defects are now
  stub/continuation fragments after side-heading extraction.
- PR-H0d proof:
  `20260531T131419Z_anthropic-small-overlap-pr-h0d-side-heading-stub-continuation-proof-v2`,
  `15` chunks, `0` failed chunks, `55` accepted operations, including `2`
  accepted `extract_side_heading_and_reattach_body` operations, verifier
  `cleaned_better` high confidence, `18` remaining issues. This proves the
  bounded single-island reattach contract, but it is not an MVP exit proof:
  heading stacks still leave continuation fragments and the run had `1` broad
  unsafe `remove_inline_noise` proposal rejected by runtime.
- PR-H0e proof:
  `20260531T151726Z_anthropic-small-overlap-pr-h0e-semantic-title-deletion-salience-proof`,
  `15` chunks, `0` failed chunks, `50` accepted operations, including `2`
  accepted `extract_side_heading_and_reattach_body` operations, verifier
  `cleaned_better` high confidence, `19` remaining issues. The broad unsafe
  `remove_inline_noise` proposal count is `0`; the semantic page-heading title
  is preserved and now needs a bounded numeric-prefix-only cleanup or
  product-limitation decision.
- PR-H0f proof:
  `20260531T162559Z_anthropic-small-overlap-pr-h0f-numeric-prefix-semantic-heading-proof-v3`,
  `15` chunks, `0` failed chunks, `56` accepted operations, including `3`
  accepted `extract_side_heading_and_reattach_body` operations and `24`
  accepted `remove_inline_noise` operations, verifier `cleaned_better` high
  confidence, `18` remaining issues. The multi-word semantic title
  `20 ДЕНЬГИ, КОТОРЫЕ ПАХНУТ?` is cleaned by removing only the exact numeric
  prefix while preserving heading text; broad unsafe `remove_inline_noise`
  remains `0`. One-word numeric-prefixed heading `21 РОТТЕРДАМ.` remains a
  policy decision.
- PR-H0g proof:
  `20260601T061315Z_anthropic-small-overlap-pr-h0g-same-block-join-heading-boundary-proof`,
  `15` chunks, `0` failed chunks, `55` accepted operations, verifier
  `cleaned_better` high confidence, `17` remaining issues,
  `heading_fused_with_body=4`, `prior_same_block_operation_not_applied=3`,
  broad unsafe `remove_inline_noise=0`. Runtime chain is available, but replay
  effectiveness is not proven.
- PR-H0h proof:
  `20260601T073422Z_anthropic-small-overlap-pr-h0h-fused-heading-targeting-proof`,
  `15` chunks, `0` failed chunks, `57` accepted operations, verifier
  `cleaned_better` high confidence, `17` remaining issues,
  `heading_fused_with_body=3`, `prior_same_block_operation_not_applied=0`,
  broad unsafe `remove_inline_noise=0`. Repeat stability
  `20260601T075435Z_anthropic-small-overlap-pr-h0h-repeat-stability` kept
  safety flat but quality variable:
  `remaining_issue_count=[21,21,17]`, `heading_fused_with_body=[4,6,1]`.
- GPT-5.4-mini same-shape control:
  `20260601T112649Z_gpt-5-4-mini-small-overlap-pr-h0h-control`, cleanup
  selector `gpt-5.4-mini`, Anthropic verifier as fixed judge, `15` chunks,
  `0` failed chunks, `26` accepted operations, `59` remaining issues,
  `heading_fused_with_body=26`, `page_furniture_inline=7`,
  `fragmented_paragraph=16`, broad unsafe `remove_inline_noise=0`. This is not
  a quality replacement for Anthropic.

PR-H0 closure decision:

- one-word numeric-prefixed heading policy, heading-stack/body-continuation, and
  leading-dash continuation artifacts remain visible limitations, not active
  micro-PR drivers;
- no H0i fused-heading salience PR; any further model-ceiling experiment must be
  an explicit comparison artifact with a stronger/different candidate, not a
  runtime repair slice;
- next active implementation workstream is PR-I1.

### PR-H. Reader Cleanup Visual Blockers / PR-H-exit

- Текущий implementation source of truth: repair backlog § Current PR-H
  Sub-Slices / PR-H0h closure. Старые PR-H1/PR-H2/PR-H2a/PR-H2b/PR-H2c/
  PR-H-final/PR-H-exit остаются history/evidence trail, но не являются
  активной next-slice формулировкой.
- Перед любым MVP exit claim устранить verifier `execution_failed` /
  `reader_verifier_remaining_issue_missing_required_text` и получить completed
  verifier evidence.
- PR-H0h repeat stability and GPT-5.4-mini control classify the current
  reader-cleanup path as safe but quality-variable. Do not continue
  fused-heading micro-PRs without fresh broad-class evidence.

Выход: PR-H is frozen as readable-draft quality boundary for the next PR-I
work. The old verifier `execution_failed` remains MVP-exit evidence debt and
must be closed before promotion, but not before starting formatting lineage.

### Current Stage, 2026-06-02

- PR-PDF3 is closed as runtime promotion for selectable-text PDFs:
  text-layer-first import is active and LibreOffice PDF fallback is deletion
  debt, not product policy.
- Images are now **release-blocking** for the text-layer PDF MVP. The
  PR-PDF3 closeout proof had `12` source image assets in preparation but
  `output_inline_shapes=0` in the final DOCX, so PR-J2 is allowed to move
  before PR-I1 under the existing image-release-blocker exception.
- Before implementation PR-J2 must first run a narrow placeholder diagnostic:
  check whether `[[DOCX_IMAGE_img_NNN]]` survives in pre-translation assembled
  Markdown, translated/runtime Markdown, reader-cleaned Markdown, and final DOCX
  text. This determines whether the fix belongs to assembly, Markdown-to-DOCX
  rebuild, or reinsertion.
- PR-J2 diagnostic result, 2026-06-02: the closeout raw Markdown has `12`
  image placeholders, reader-cleaned Markdown has `0`, and final DOCX has
  `0` placeholder paragraphs / `0` inline shapes / `0` media files. The owner
  is reader-cleanup -> DOCX-rebuild handoff. The low-level reinsertion helper
  is not the first failing layer because it never receives textual anchors.
- PR-J2 local implementation, 2026-06-02: restore missing image placeholder
  blocks from raw cleanup Markdown into rebuild-only Markdown for final DOCX
  generation. Reader-facing cleaned Markdown remains placeholder-free.
- PR-J2 clean proof, 2026-06-02:
  `20260602T_pr_j2_image_reinsertion_proof` succeeded. The proof PDF now has
  `12` prepared image assets -> `12` final inline shapes / `12` DOCX media
  files with `output_contains_placeholder_markup=False`.
- Reader cleanup remains reader-facing polish, not source cleanup and not image
  or formatting repair. Do not move images into cleanup prompts and do not
  downgrade reader cleanup to fallback until the post-PR-J/PR-I A/B proof says
  it is safe.

### PR-J2. Image Reinsertion Fix

- **Completed locally on 2026-06-02 for the text-layer PDF proof path.**
- PR-J2 diagnostic gate:
  - Source evidence: preparation sees nonzero PDF image assets (`12` on the
    chapter-region proof).
  - Placeholder evidence: count `[[DOCX_IMAGE_img_NNN]]` in generated/assembled
    Markdown before translation, translated runtime Markdown, reader-cleaned
    Markdown, and final DOCX text before reinsertion.
  - Reinsertion evidence: inspect `image_reinsertion_placeholder_unhandled`,
    placeholder integrity, processed image assets, and final inline shape count.
- Diagnostic status: confirmed on the PR-PDF3 closeout artifacts. Placeholder
  loss happens after raw reader-cleanup Markdown and before final DOCX
  reinsertion, because cleaned Markdown omitted all `12` image placeholder
  blocks.
- PR-J2 implementation target:
  - Preserve image placeholder blocks through translation assembly and DOCX
    rebuild, or reattach them from source/image registry when the translated
    Markdown intentionally omits non-translatable image blocks.
  - Current local fix chooses the rebuild-only reattach path after reader
    cleanup: final DOCX rebuild receives missing placeholder blocks, but UI
    cleaned Markdown stays free of internal image tags.
  - Keep images as non-translatable structural blocks; do not ask reader cleanup
    to recover images.
  - Initial proof target is `>0` final inline shapes with
    `image_reinsertion_placeholder_unhandled=0`; acceptance target is source
    image assets matching final inline shapes where the source document has
    stable extractable images.
- Clean proof result:
  `20260602T_pr_j2_image_reinsertion_proof` restored the proof PDF from
  `output_inline_shapes=0` to `output_inline_shapes=12`, with `12` DOCX media
  files and no visible placeholder markup in the final DOCX.

Выход: text-layer PDF final DOCX contains reinjected source images or the exact
upstream blocker is recorded with evidence.

### PR-I1 / PR-I2. Formatting Preservation

- **Current local slice: PR-I1b.** PR-I1 proved cleanup-aware lineage can be
  derived through image-placeholder gaps; PR-I1b now carries paragraph identity
  through cleanup blocks and switches the formatting/image stitches to id-first
  matching with normalized-text fallback. Focused tests cover the text-drift
  case; real-document identity evidence is still pending because the older PR-I1
  proof artifacts do not contain `cleanup_identity_*` counters.
- PR-I1: реализовать и протестировать lineage contract
  source paragraphs / raw generated registry → reader-cleaned Markdown blocks →
  generated paragraphs/runs/styles used by DOCX rebuild.
- PR-I1 acceptance:
  - formatting diagnostics can explain which cleaned DOCX paragraphs map back to
    source paragraph ids after reader cleanup;
  - reader cleanup split/join/delete operations do not silently destroy
    heading/list/emphasis lineage;
  - anchor-repair operation lineage is skipped explicitly until a later slice can
    map post-first-pass block ids without guessing;
  - mapping failures are diagnostic evidence, not guessed formatting repair.
- PR-I2: применить lineage в DOCX writer/rebuild path для bold/italic/emphasis,
  heading/subheading styles, list styling/numbering, superscript/subscript,
  hyperlinks, and line/page breaks only where source evidence exists.
- Не пытаться восстановить formatting из plain cleaned Markdown без source
  evidence и lineage.

Выход: reader-first DOCX сохраняет book-grade formatting настолько, насколько
это подтверждено source evidence.

### PR-J1 / PR-J2. Image Handoff/Reinsertion

- PR-J1: completed locally for text-layer PDFs. The importer/generated-DOCX
  bridge now exposes PDF-origin image objects to preparation.
- PR-J2: completed locally for the proof PDF. Reader-cleanup DOCX rebuild
  restores missing image placeholder blocks into rebuild-only Markdown; source
  image assets now become final inline shapes without prompt repair.

Выход: image policy имеет explicit release decision: fixed, upstream-blocked или
not release-blocking.

### PR-A0. Reader Cleanup Config Surface

- Завершить canonical config surface для reader cleanup в `config.toml` и
  `core/config*.py`. Уже существует root-level `reader_cleanup_model` /
  `reader_verifier_model`; не дублировать его. Недостающие поля:
  `reader_cleanup_default`, `reader_cleanup_chunk_size`,
  `reader_cleanup_global_plan_enabled`, `reader_cleanup_policy`, safety budgets,
  `reader_cleanup_keep_toc`, `reader_cleanup_drop_back_matter`.
- Добавить env compatibility в `.env.example` и config loader.
- Синхронизировать `validation/profiles.py`: profile overrides должны отличаться
  от UI defaults, но использовать те же field names.
- Добавить tests для config defaults, env overrides, profile resolution и
  `apply_runtime_resolution_to_app_config`.

Выход: `reader_cleanup_default = true` становится реальным product setting, а не
только полем, которое validation умеет читать.

### PR-A1. Reader-First Default Promotion

- В `config.toml`: `structure_recognition.mode = "off"` как дефолт.
- Включить `reader_cleanup_default = true` для `translate`, но оставить user
  toggle и profile overrides.
- Проверить, что `_resolve_structure_recognition_mode` и preparation доходят до
  финального Markdown в режиме `off` без segment-required / DocumentMap-required /
  chapter-reassembly ошибок.
- Явно проверить, что `structure_recovery.enabled = true` больше не трактуется
  как включение Stage 1/2. Если deterministic source cleanup остаётся, ему нужен
  отдельный neutral name или explicit transition note.

Выход: основной runtime path не требует DocumentMap/StructureMap.

### PR-A2. UI Reader Report + Structure Panel Decoupling

- Добавить в `ui/_ui.py` sidebar-чекбокс `Reader cleanup post-pass`
  (рядом с `translation_second_pass`/`audiobook_postprocess`), пробросить в
  app_config (`reader_cleanup_enabled` и связанные поля из MVP-spec § Minimal
  New Config).
- В `ui/_app.py` сохранять `reader_cleanup_enabled` так же явно, как
  `translation_second_pass_enabled` и `audiobook_postprocess_enabled`.
- Перед удалением `ui/structure_review_panel.py` вынести используемые helpers
  selection/retry/context-policy/payload/settings-hash/segment expansion в
  neutral module. Только после этого заменить visual panel на reader-cleanup
  отчёт (raw vs cleaned + report summary).
- Surface артефактов: убедиться, что `ui_result_artifacts_saved` несёт cleaned
  как primary, raw + `reader_cleanup_report_path` как diagnostic.

Выход: пользователь может включать/выключать reader cleanup в UI, а структура
не остаётся скрытым review bottleneck.

### PR-A3. Anchor Repair Decision

- Зафиксировать домашнюю точку для anchor repair:
  - либо включить в основном пайплайне через `reader_cleanup_anchor_repair_enabled`
    с полным DOCX rebuild path;
  - либо оставить diagnostic-only и не подавать targets в runtime.
- Если runtime anchor repair включается, определить production source of targets:
  verifier output, persisted review artifact, manual review selection или
  explicit run-profile input.
- Не оставлять validation-only repair (контракт PR-G).

Выход: anchor repair имеет один owner и один artifact contract.

### PR-GATE. Decision Gate

- По § Decision Gate MVP-spec выбрать: promote как основной режим / только
  audiobook-continuous / drop.
- Для замены structure-first целевой исход — **promote**.
- Decision record должен включать exact evidence: proof doc, дополнительный
  документ, UI artifact paths, cleanup report stats, formatting/image decisions.

## 5. План очистки и архивации тупиковой фазы (Decommission PRs)

Runtime/code decommission выполняется ТОЛЬКО после PR-A1 + PR-A2
(reader-first default доказан и в UI), чтобы не сломать рабочий продукт. Порядок
— от развязки контрактов к удалению файлов.

Исключение: PR-DOC0/PR-DOC1 freeze/docs archive preparation может стартовать
раньше PR-GATE, если не удаляет active runtime code и явно помечена как
pre-decommission documentation work.

### PR-DOC0. Freeze Structure-First Surface

- Запретить новые Stage 1/Stage 2/topology tuning PRs.
- Заморозить structure-specific run profiles как historical/archival.
- Добавить temporary static guard, что production/default profiles не включают
  `structure_recognition_mode = "always"`.

### PR-DOC1. Заморозка и архивация документации

Перенесено в `docs/archive/specs/` 2026-05-30 как `dead-end / superseded`,
с записью в `docs/ARCHIVE_INDEX.md`:

- `docs/archive/specs/STRUCTURE_RECOGNITION_PR_BACKLOG_2026-05-21.md`
- `docs/archive/specs/STRUCTURE_RECOGNITION_INPUT_FIDELITY_SPEC_2026-05-21.md`
- `docs/archive/specs/STRUCTURE_RECOGNITION_SETTINGS_EXPERIMENT_PLAN_2026-05-21.md`
- `docs/archive/specs/OUTPUT_DISPLAY_HYGIENE_AND_STRUCTURE_DETECTORS_SPEC_2026-05-21.md`
- `docs/archive/specs/AI_FIRST_STRUCTURE_RECOVERY_SPEC_2026-05-08.md`
- `docs/archive/specs/CHAPTER_WORKFLOW_CONTRACT_ALIGNMENT_SPEC_2026-05-07.md`

Контракт архивации: соблюсти условия из `ARCHIVE_INDEX.md` (реализация/закрытие
зафиксированы, канонические доки обновлены, есть запись в индексе).

### PR-D0. Preparation/Data-Model Decoupling

До удаления `src/docxaicorrector/structure/`:

- Убрать direct imports `docxaicorrector.structure.*` из active off-path в
  `processing/preparation.py`.
- Сократить active `PreparedDocumentData` contract: reader-first path не должен
  требовать `document_map`, `document_topology_projection`, `structure_map`,
  `structure_validation_report`.
- Если compatibility fields временно остаются, они должны быть no-op/empty и не
  участвовать в production decision-making.
- Убрать structure settings из preparation cache key после того, как они стали
  no-op, иначе cache продолжит кодировать мёртвую конфигурацию.
- Разделить `core.models`: оставить source-shape/paragraph metadata, но вынести
  или удалить AI-recognition-only модели после прекращения импортов.

Выход: `prepare_document_for_processing(..., structure_recognition.mode=off)`
не импортирует и не требует Stage 1/2 modules.

### PR-D0-UI. UI/Chapter Workflow Decoupling

- Вынести из `ui/structure_review_panel.py` reusable helpers:
  selected processing state, retry failed processing state, context policy,
  selected processing payload, structure/settings hash replacement,
  segment expansion.
- Проверить `chapter_workflow/service.py`: если он нужен reader-first selected
  output flow, оставить neutral workflow; если он только structure-first review
  surface, удалить после UI replacement.
- Удалить visual structure review panel только после сохранения selection/retry
  behavior.

### PR-D1. Очистка конфигурации

- До удаления кода перевести в deprecated/no-op все три семьи structure config:
  `structure_recognition`, `structure_recovery`, `structure_validation`.
- Если deterministic source cleanup остаётся, создать новый neutral config block
  (например source cleanup/layout hygiene), а не продолжать использовать
  `structure_recovery.enabled`.
- Старые config/env keys должны быть compatibility no-op, не hard error.
- `DOCX_AI_STRUCTURE_RECOGNITION_*`, `DOCX_AI_STRUCTURE_RECOVERY_*`,
  `DOCX_AI_STRUCTURE_VALIDATION_*` в `.env.example` сначала явно пометить как
  deprecated; физическое удаление делать после compatibility window.
- Structure-поля в `validation/profiles.py` и run-profile-ах
  `corpus_registry.toml` сначала сделать ignored/deprecated для active profiles,
  кроме archived historical profiles.
- Model role `structure_recognition` удалять из `core/config_model_registry.py`
  только после удаления всех consumers в PR-D2; в PR-D1 он должен стать
  compatibility/deprecated surface, а не active production dependency.

### PR-D2. Удаление Stage 1/1.5/2 кода

После PR-D0/PR-D0-UI и PR-D1 удалить (с git-историей как архивом)
изолированные модули:

- Пакет `src/docxaicorrector/structure/` целиком:
  `recognition.py`, `document_map.py`, `topology.py`, `reconciliation.py`,
  `layout_signals.py`, `page_furniture_detection.py`, `validation.py`,
  `_responses_timeout.py`.
- Stage 1/1.5/2 оркестрацию в `processing/preparation.py`:
  `_run_document_map_stage`, `_run_document_topology_projection_stage`,
  `_run_structure_recognition`, reconciliation/debug/cache branches, window
  settings и fallback state.
- DocumentMap-dependent ветки в `document/relations.py`, `segments.py`,
  `semantic_blocks.py`, `boundaries.py`.
- Structure-only части `src/docxaicorrector/document/`:
  `structure_authority.py`, `structure_repair.py`, `roles.py`,
  `boundary_review.py`, если audit докажет, что они больше не нужны reader-first
  extraction/source cleanup.

Важно: удаление вести итеративно «лист за листом», каждый шаг — targeted tests,
`git diff --check`, затем full canonical verification на финале.

### PR-D2-Prompts. Промпты

Архивировать/удалить неиспользуемые промпты:

- `prompts/structure_recognition_system.txt`
- `prompts/document_map_system.txt`
- `prompts/scene_graph_extraction.txt`
- `prompts/reconciliation_targeted_system.txt`

Сначала grep по коду и tests — убедиться, что ни один prompt не грузится
reader-first путём.

### PR-D2-Validation. Валидация и бенчмарки

- Разделить validation cleanup:
  - удалить AI-structure validation/gates, которые завязаны на Stage 1/2;
  - сохранить или переименовать deterministic structural tier, если он фактически
    проверяет extraction/Markdown/DOCX roundtrip без LLM.
- Архивировать `benchmark_projects/structure_recognition_benchmark/`.
- Удалить/перенести тесты: `test_structure_*`, `test_document_structure_*`,
  `test_real_document_structure_recognition_integration.py`,
  `test_structure_recognition_benchmark_runner.py`,
  `test_structure_layout_signals.py` и др.
- Обновить `test_real_document_validation_corpus.py`, `test_typecheck.py`,
  `test_script_contract_static.py`, чтобы они не ожидали активный
  structure-first surface.

### PR-D3. Обновление канонических доков

- `README.md`, `docs/WORKFLOW_AND_IMAGE_MODES.md`,
  `docs/REAL_DOCUMENT_VALIDATION_WORKFLOW.md`,
  `docs/AI_AGENT_DEVELOPMENT_RULES.md`, `AGENTS.md` — убрать structure-first как
  активный путь, описать reader-first как основной.
- Снять structural-diagnostic routing из AGENTS только в части тупиковой
  Stage 1/2 фазы. Если deterministic source/roundtrip diagnostic остаётся,
  переименовать его и обновить command contract.

## 6. PR Backlog

Этот backlog превращает план в order-of-implementation. Future PRs должны
называть ровно один scope; если slice обнаруживает defect другого owner-а, он
фиксирует evidence и останавливается вместо расширения PR.

| PR | Scope | Required outcome |
| --- | --- | --- |
| PR-M0 | Plan Refresh + Inventory Lock | Обновить PR-H-exit status, latest completed proof evidence, inventory table, stop rules. |
| PR-A0 | Reader Cleanup Config Surface | Complete missing config/env/UI-default/profile fields for reader cleanup; keep existing `reader_cleanup_model` / `reader_verifier_model`; tests for defaults/overrides. |
| PR-H0 | Canonical Small-Overlap + Shared Blind Spots | Closed locally as quality boundary: canonical small-overlap shape is config/runtime/profile default; Anthropic is cleanup leader; H0h repeat stability is safe but quality-variable; `gpt-5.4-mini` same-shape control is not competitive. |
| PR-H0a | Inline Marker + Duplicate Heading Runtime Proof | Completed locally: Anthropic canonical proof run has `failed_chunk_count=0`, `noise_substring_not_found=0`, raw `4.0` -> cleaned `6.0`; inline markers closed; duplicate heading is runtime-covered but needs operation selection/pre-audit targeting. |
| PR-H0b | Operation Selection Targets Runtime Proof | Completed locally: duplicate semantic heading targeting is selected and accepted; side-heading islands still need operation-choice salience. |
| PR-H0c | Side-Heading Operation Choice Salience | Completed locally: side-heading proof examples move to accepted `split_block`; remaining issue is stub/continuation fragments after extraction. |
| PR-H0d | Side-Heading Stub/Continuation Contract | Completed locally: new bounded `extract_side_heading_and_reattach_body` operation accepted in replay for single heading-island sentence interruptions; heading stacks and one broad unsafe `remove_inline_noise` proposal remain. |
| PR-H0e | Semantic-Title / Page-Heading Deletion Salience | Completed locally: broad unsafe `remove_inline_noise` proposals dropped to `0`; semantic title is preserved, with numeric-prefix cleanup handed off to PR-H0f. |
| PR-H0f | Numeric-Prefix Semantic Heading Cleanup | Completed locally: multi-word isolated semantic heading prefix cleanup preserves title text, removes only exact numeric prefix, keeps broad unsafe `remove_inline_noise=0`; one-word heading policy remains. |
| PR-H | Reader Cleanup Visual Blockers / PR-H-exit | Frozen as readable-draft quality boundary for PR-I start; old verifier `execution_failed` remains MVP-exit evidence debt, but no H0i fused-heading micro-PR. |
| PR-PDF0 | Source Import Quality Gate | Completed locally: permissive text-layer probe on chapter-region PDF is `decision=promising` with dense body text and source structure signals; use as evidence for PR-PDF1, not production promotion. |
| PR-PDF1 | Text-Layer PDF Importer | Completed locally as generated-DOCX bridge: `PdfTextSpan -> ParagraphUnit`, page furniture/page numbers/blank-page notices filtered, bounded TOC blocks, `124` paragraphs, `0` page-number-like leakage, `0` markdown emphasis markers. Direct `PDF -> ParagraphUnit -> preparation` remains target architecture after broader proof. |
| PR-PDF3 | Text-Layer Default Promotion | Closed locally: text-layer-first is the runtime path for selectable-text PDF imports; LibreOffice fallback/legacy override has been removed from runtime. Direct ParagraphUnit import, residual page-furniture quality gate, final-DOCX image handoff, and deletion cleanup for remaining diagnostic LibreOffice PDF references are follow-ups. |
| PR-PDF4 | Remove Historical LibreOffice PDF Debt | Future cleanup after image/formatting proof: delete remaining LibreOffice PDF helper/comparison-only tests/docs; keep legacy `.doc` LibreOffice support separate. |
| PR-PDF2 | OCR Fallback | Deferred for now: partial plumbing exists behind `DOCXAI_PDF_OCR_IMPORT_ENABLED=1`, but scanned PDFs are not required for the current text-layer MVP proof. |
| PR-I1 | Formatting Lineage Contract | Completed locally as runtime-contract proof: reader cleanup postprocess receives the assembly registry and derives lineage through sparse image-placeholder gaps (`123` raw cleanup blocks vs `111` registry entries, `12` image gaps, `108` derived registry entries, `16` applied cleanup lineage ops). Images stay `12/12`; formatting acceptance still fails, so PR-I2 must focus on formatting application/diagnostics, not lineage availability. |
| PR-I1b | Identity-Anchored Cleanup Stitch | Active locally: cleanup blocks carry internal paragraph identity without model-payload leakage; formatting lineage and rebuild-only image placeholder stitching now use id-first matching with text fallback. Focused tests pass; next step is short lineage/rebuild harness or milestone proof for real-document counters. |
| PR-I2 | Formatting Preservation Implementation | Apply lineage in DOCX writer/rebuild path; preserve book-grade styles. |
| PR-J1 | Image Handoff Evidence | Completed locally for text-layer PDFs: initial text-only bridge loss was identified and the generated-DOCX bridge now exposes PDF-origin image objects to preparation; LibreOffice media are not extractor-visible assets. |
| PR-J2 | Image Reinsertion Fix | Completed locally for the proof PDF: placeholder survival diagnostic identified reader-cleanup -> DOCX-rebuild handoff loss; rebuild-only Markdown now restores missing image placeholders, producing `12/12` final inline shapes with no visible placeholder markup. |
| PR-A1 | Reader-First Default Promotion | `structure_recognition.mode=off`, reader cleanup default-on, proof + extra doc + UI evidence. |
| PR-A2 | UI Reader Report + Structure Panel Decoupling | Reader cleanup checkbox/report; selection/retry helpers extracted from structure panel. |
| PR-A3 | Anchor Repair Decision | Runtime owner/source-of-targets or diagnostic-only decision recorded and tested. |
| PR-GATE | Decision Gate | Explicit promote/audiobook-only/drop decision with proof doc, extra doc, UI artifacts, cleanup stats, formatting/image decisions. |
| PR-DOC0 | Freeze Structure-First Surface | Stop new Stage 1/2/topology tuning; freeze structure profiles; guard defaults from `always`. |
| PR-DOC1 | Archive Structure-First Docs | Archive dead-end docs and update `ARCHIVE_INDEX.md`; may run before runtime decommission if docs-only. |
| PR-D0 | Preparation/Data-Model Decoupling | Active reader-first preparation no longer imports/requires Stage 1/2 models. |
| PR-D0-UI | UI/Chapter Workflow Decoupling | Shared selection/retry helpers extracted; structure panel removable without behavior loss. |
| PR-D1 | Config/Profile Migration | Structure config families deprecated/no-op or renamed; run profiles cleaned. |
| PR-D2 | Code Decommission | Remove structure package and Stage 1/2 orchestration after decoupling. |
| PR-D2-Prompts | Prompt Decommission | Archive/delete structure prompts after grep confirms no reader-first consumer. |
| PR-D2-Validation | Validation/Benchmark/Test Decommission | Remove or rename AI-structure validation, benchmark, and tests after deterministic tiers are classified. |
| PR-D3 | Canonical Docs + AGENTS Cleanup | Docs describe reader-first as primary and remove/rename old structural routing. |

## 7. Последовательность и зависимости

```text
PR-M0 (plan/status/inventory)
  -> PR-A0 (reader cleanup config surface)
  -> PR-H0 closure (small-overlap reader-cleanup quality boundary)
  -> PR-PDF0 (source import quality gate; completed locally)
  -> PR-PDF1 (text-layer PDF importer bridge)
  -> PR-PDF3 (text-layer runtime promotion; LibreOffice fallback removed)
  -> PR-PDF2 (OCR fallback deferred for scanned/empty text-layer PDFs)
  -> PR-J2 (image placeholder diagnostic + final DOCX reinsertion fix; completed locally)
  -> PR-I1 (formatting lineage; completed local runtime proof)
  -> PR-I1b (identity-anchored cleanup stitch; id-first local switch active)
  -> PR-I2 (formatting preservation implementation)
  -> PR-A1 (reader-first default promotion)
  -> PR-A2 (UI reader report + structure panel decoupling)
  -> PR-A3 (anchor repair home)
  -> PR-GATE (Decision Gate: promote/audiobook-only/drop)
        -> PR-DOC0/PR-DOC1 (freeze + archive docs; may be docs-only earlier)
        -> PR-D0 (preparation/data-model decoupling)
        -> PR-D0-UI (UI/chapter workflow decoupling)
        -> PR-D1 (config/profile migration)
        -> PR-D2/PR-D2-Prompts/PR-D2-Validation (code/prompts/benchmarks/tests)
        -> PR-D3 (canonical docs)
```

Жёсткое правило: runtime/code decommission PR-D0+ не начинается раньше, чем
PR-A1+PR-A2 доказаны user-visible verification (не только agent-side).

## 8. Риски и митигации

- **Скрытые зависимости extraction/translation от structure-модулей.** Митигация:
  PR-D0 decoupling до удаления файлов; grep импортов недостаточен, нужен
  inventory по DTO/cache/config/UI/test consumers.
- **`structure_recognition.mode=off` даёт ложное чувство удаления structure.**
  Митигация: отдельно решить судьбу `structure_recovery` и `structure_validation`;
  deterministic source cleanup переименовать или задокументировать как активный
  reader-first слой.
- **UI panel removal ломает selected processing/retry behavior.** Митигация:
  сначала extracted neutral helpers, потом visual replacement.
- **Reader cleanup default включён только в validation profiles, но не в app
  config/UI.** Митигация: PR-A0 config surface перед promotion.
- **Reader verifier падает с `execution_failed`.** Митигация: считать такой run
  невалидным для MVP exit независимо от pipeline success/no-harm gates. Следующий
  шаг для promotion evidence — изолировать причину verifier failure / missing
  required text в focused test или replay before any MVP-exit proof claim. Это
  не блокирует старт PR-I1, потому что PR-I не заявляет promotion readiness.
- **Новый PR-H-exit code path не применяется на real-doc.** Митигация:
  `heading_boundary_normalized_across_adjacent_block=0` означает, что path
  code-ready but unproven. Следующий PR-H proof должен либо показать accepted
  usage (`>0`), либо задокументировать, почему remaining sites принадлежат
  другому owner-у/contract decision.
- **Formatting preservation невозможно восстановить из plain cleaned Markdown.**
  Митигация: PR-I1 lineage contract до PR-I2 implementation.
- **Image loss чинится не в том слое.** Митигация: PR-J1 evidence slice должен
  найти loss point до любого fix.
- **Off-path не доходит до финального Markdown.** Митигация: PR-A1 повторяет
  Slice 0 discovery как регрессионный тест.
- **Старые config.toml/.env ломаются после PR-D1.** Митигация: deprecation no-op
  для удалённых ключей вместо жёсткой ошибки на compatibility window.
- **CI/typecheck падает из-за висячих импортов.** Митигация: каждый под-шаг
  PR-D0/PR-D1/PR-D2/PR-D2-Validation завершать targeted tests,
  `git diff --check`, а финал — canonical full verification.

## 9. Верификация

- Перед финальной верификацией всегда `git status --porcelain`; dirty worktree
  явно помечает локальные результаты как potentially non-CI-parity.
- Каждая фаза PR-A*/PR-H/PR-I*/PR-J*: focused tests:
  `bash scripts/test.sh tests/test_reader_cleanup_mvp.py -q`,
  `bash scripts/test.sh tests/test_real_document_pipeline_validation.py -q -k 'reader_verifier or comparison_only'`,
  плюс targeted tests для config/UI/formatting/image touched areas.
- Финал promotion: comparison-only proof document +
  минимум один дополнительный real-document profile; проверить `cleaned_better`,
  `failed_chunk_count=0`, отсутствие false deletions/readability regressions,
  formatting/image gates по принятой release policy.
- Любой promotion/MVP-exit proof с `reader_verifier_status=failed` или
  `reader_verifier_reason=execution_failed` считается invalid proof. Сначала
  исправить verifier precondition, затем повторить completed proof.
- Для PR-H-exit отдельно проверять operation evidence:
  `heading_boundary_normalized_across_adjacent_block > 0` либо explicit decision
  record, что adjacent/split path не является нужным owner-ом для remaining
  sites.
- Финал UI: user-visible UI прогон с reader cleanup, проверка
  `ui_result_artifacts_saved` (cleaned primary + raw/report).
- Каждая decommission фаза PR-D*: targeted tests вокруг удаляемого слоя, затем
  `bash scripts/test.sh tests/ -q` (в WSL runtime) + `git diff --check`.
- Decommission считается завершённым, когда: Stage 1/1.5/2 код удалён или
  архивирован, reader-first путь зелёный, канонические доки обновлены, архивные
  записи внесены в `ARCHIVE_INDEX.md`.

## 10. Out of Scope

- Любой ре-тюнинг Stage 1/Stage 2/topology (фаза закрыта, не чинится).
- Document-specific regex/phrase lists в reader cleanup (запрещено MVP-spec).
- Изменение acceptance-порогов ради «зелёного» comparison-only прогона.
- Broad pre-translation rewrite под видом source cleanup. Source cleanup может
  удалять только очевидные non-semantic artifacts с reliable page-boundary /
  repetition / extraction evidence и audit report.
- Удаление deterministic extraction/roundtrip infrastructure только потому, что
  оно использует слово `structure` в имени. Сначала определить owner и runtime
  usefulness, затем переименовать или удалить.
- Удаление `structure_recovery.enabled` и связанных deterministic source-cleanup
  веток без audit не входит в scope. В scope входит их переименование/перенос в
  neutral source cleanup/layout hygiene owner, если audit подтверждает, что они
  нужны reader-first path.
