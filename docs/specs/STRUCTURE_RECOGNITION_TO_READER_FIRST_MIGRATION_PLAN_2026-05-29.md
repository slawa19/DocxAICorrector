# Structure-Recognition → Reader-First Migration Plan

Date: 2026-05-29
Status: Active migration plan; structure-first tuning specs archived 2026-05-30

Связанные источники истины:

- `docs/specs/SIMPLE_READER_FIRST_MVP_SPEC_2026-05-21.md`
- `docs/specs/SIMPLE_READER_FIRST_MVP_REPAIR_PR_BACKLOG_2026-05-23.md`
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

- **PR-H0/PR-H0a/PR-H0b/PR-H0c завершены локально**: canonical
  small-overlap форма (`chunk_size=8000`, `3/3` read-only overlap,
  `global_plan_enabled=false`) зафиксирована как runtime/config/profile канон,
  inline markers закрыты, duplicate semantic heading targeting доказан, а
  side-heading operation choice переведён с unsafe `remove_inline_noise` на
  accepted `split_block` для proof examples. Следующий узкий PR-H slice — не
  model bakeoff, а side-heading stub/continuation contract; verifier остаётся
  observer-only.
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
- По May 26/30 evidence следующий полезный шаг внутри PR-H — сначала устранить
  verifier `execution_failed` / missing required text precondition, затем сделать
  fresh source-cleanup-remove comparison run и только после этого решать, является
  ли остаток PR-H operation-selection/contract problem или product-accepted
  readable-draft limitation.
- **PR-I (Formatting Preservation)** не начата. Это не только DOCX-writer work:
  нужен lineage contract raw Markdown block → cleaned block(s) → final DOCX
  paragraphs/runs для headings, lists, emphasis и source properties.
- **PR-J (Image Handoff/Reinsertion)** не начата. Нужен evidence slice, где
  именно исчезают PDF-origin images/placeholders/assets/inline shapes.
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
PR-H-exit unblock/proof → PR-I (→ PR-J) → reader cleanup config/UI promotion →
Decision Gate.

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

Промежуточный PR между model bake-off и PR-H-exit runtime proof.

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
следующий runtime PR-H-exit работает уже поверх small-overlap канона, а не
поверх старой bulk/current формы.

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

Remaining PR-H targets:

- side-heading stub/continuation contract after heading-island extraction;
- leading-dash continuation artifacts as a separate classification decision.

### PR-H. Reader Cleanup Visual Blockers / PR-H-exit

- Текущий implementation source of truth: repair backlog § PR-H-exit
  Adjacent/Split Heading Operation Contract. Все PR-H sub-slices
  (PR-H1/PR-H2/PR-H2a/PR-H2b/PR-H2c/PR-H-final/PR-H-exit) остаются историей и
  evidence trail; текущий blocker — PR-H-exit proof failure.
- Перед любым MVP exit claim устранить verifier `execution_failed` /
  `reader_verifier_remaining_issue_missing_required_text` и получить completed
  verifier evidence.
- Довести PR-H до stable visual baseline:
  - сохранить `reader_cleanup_failed_chunk_count = 0`;
  - доказать, что retained adjacent/split heading path либо применяется на
    real-doc (`heading_boundary_normalized_across_adjacent_block > 0`), либо
    явно классифицирован как not-useful для remaining sites;
  - закрыть или классифицировать fused heading / fragmented paragraph anchors;
  - проверить source-side page-furniture cleanup hypothesis отдельным audited
    source-cleanup slice, не превращая его в broad pre-translation rewrite;
  - не расширять runtime safety guards без evidence, что AI предлагает valid
    bounded operations, которые code rejected too narrowly.

Выход: PR-H имеет valid verifier proof или explicit product decision о
readable-draft limitation; текущий `execution_failed` больше не блокирует
evidence.

### PR-I1 / PR-I2. Formatting Preservation

- PR-I1: реализовать lineage contract raw blocks → cleaned blocks → generated
  paragraphs/runs/styles.
- PR-I2: применить lineage в DOCX writer/rebuild path для bold/italic/emphasis,
  heading/subheading styles и list styling/numbering.
- Не пытаться восстановить formatting из plain cleaned Markdown без source
  evidence и lineage.

Выход: reader-first DOCX сохраняет book-grade formatting настолько, насколько
это подтверждено source evidence.

### PR-J1 / PR-J2. Image Handoff/Reinsertion

- PR-J1: если картинки release-blocking, найти точку потери PDF-origin
  `image_count`, placeholders, processed assets или output inline shapes.
- PR-J2: восстановить handoff/reinsertion в правильном слое pipeline; не чинить
  images через reader cleanup prompt.

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
| PR-H0 | Canonical Small-Overlap + Shared Blind Spots | Completed locally: canonical small-overlap shape is config/runtime/profile default; shared Anthropic/Gemini blind spots are explicit target classes. |
| PR-H0a | Inline Marker + Duplicate Heading Runtime Proof | Completed locally: Anthropic canonical proof run has `failed_chunk_count=0`, `noise_substring_not_found=0`, raw `4.0` -> cleaned `6.0`; inline markers closed; duplicate heading is runtime-covered but needs operation selection/pre-audit targeting. |
| PR-H0b | Operation Selection Targets Runtime Proof | Completed locally: duplicate semantic heading targeting is selected and accepted; side-heading islands still need operation-choice salience. |
| PR-H0c | Side-Heading Operation Choice Salience | Completed locally: side-heading proof examples move to accepted `split_block`; remaining issue is stub/continuation fragments after extraction. |
| PR-H | Reader Cleanup Visual Blockers / PR-H-exit | Next runtime slice after PR-H0c: side-heading stub/continuation contract; no verifier-side repair; keep stable `failed_chunk_count=0` and no false deletions. |
| PR-I1 | Formatting Lineage Contract | Raw→cleaned→DOCX mapping для headings/lists/emphasis/source props; focused tests. |
| PR-I2 | Formatting Preservation Implementation | Apply lineage in DOCX writer/rebuild path; preserve book-grade styles. |
| PR-J1 | Image Handoff Evidence | Найти точку потери PDF-origin images/placeholders/assets/inline shapes. |
| PR-J2 | Image Reinsertion Fix | Restore image handoff/reinsertion if release-blocking. |
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
  -> PR-H (PR-H-exit verifier unblock + visual cleanup/source-cleanup evidence)
  -> PR-I1/PR-I2 (formatting lineage + implementation)
  -> [PR-J1/PR-J2 if images are release-blocking]
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
  шаг — изолировать причину verifier failure / missing required text в focused
  test или replay before any new proof claim; не переходить к PR-I/PR-A1 как к
  promotion evidence, пока verifier не завершён.
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
