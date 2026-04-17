# Archive Index

Этот документ является явным архивным разделом для `docs/`. Всё, что перечислено ниже, полезно как исторический, refactor- или review-контекст, но не является текущим source of truth.

Жёсткое правило размещения документов:

1. новые активные документы должны создаваться внутри канонической структуры `docs/`, а не в `docs/archive/`;
2. корень `docs/` зарезервирован под верхнеуровневую каноническую документацию репозитория;
3. тематические активные документы нужно складывать в релевантные подпапки вроде `docs/testing/` и `docs/reviews/`, а не разбрасывать в корне;
4. `docs/archive/` предназначен только для исторических, superseded и уже реализованных материалов, которые сохраняются для контекста;
5. перенос документа в archive означает, что он больше не является местом для активной разработки и не должен использоваться как default location для новых workstream-ов.

Правило приоритета:

1. Для runtime workflow и image modes приоритет всегда у `docs/WORKFLOW_AND_IMAGE_MODES.md`.
2. Для общего пользовательского и архитектурного overview приоритет у `README.md`.
3. Всё ниже считается archived, superseded или point-in-time материалом.

## Current Sources Of Truth

- `README.md`
- `docs/ARCHIVE_INDEX.md`
- `docs/WORKFLOW_AND_IMAGE_MODES.md`
- `docs/STARTUP_PERFORMANCE_CONTRACT.md`
- `docs/AI_AGENT_DEVELOPMENT_RULES.md`
- `docs/testing/REAL_DOCUMENT_VALIDATION_WORKFLOW.md`
- `docs/testing/UNIVERSAL_TEST_SYSTEM_MAINTENANCE_GUIDE_2026-03-21.md`

## Current Folder Layout

- `docs/` — only top-level canonical repository docs
- `docs/testing/` — active testing and validation maintenance docs
- `docs/reviews/` — review handoffs, review reports, and review specs
- `docs/archive/` — historical, superseded, or realized materials

## Archived Specs And Plans

- `docs/archive/specs/ARCHITECTURE_REFACTORING_SPEC_2026-03-25.md` — implemented and archived 2026-04-17 after the architecture refactoring wave completed and was re-verified through visible task runs
- `docs/archive/specs/AI_STRUCTURE_RECOGNITION_SPEC_2026-03-26.md` — implemented and archived 2026-04-17 after Phase 1 plus the scoped Phase 2/3 follow-up landed; remaining heuristic-only reduction is future follow-up work, not an active blocking item
- `docs/archive/specs/ACTIVE_SPEC_CHECKLIST_2026-04-17.md` — archived 2026-04-17 as the completion record for the paired architecture and AI implementation wave
- `docs/archive/specs/UNIVERSAL_REAL_DOCUMENT_VALIDATION_SPEC_2026-03-21.md` — archived 2026-04-16 after the architecture landed; kept as historical design and review context
- `docs/archive/specs/RELATION_NORMALIZATION_SPEC_2026-03-27.md` — archived 2026-04-16 because the maintained relation-normalization implementation lives in code/tests and the root copy was no longer an active source of truth
- `docs/archive/specs/PARAGRAPH_BOUNDARY_NORMALIZATION_SPEC_2026-03-27.md` — implemented and archived 2026-03-28
- `docs/archive/specs/DOCX_FORMATTING_HARDENING_SPEC_2026-03-13.md` — implemented 2026-03-13
- `docs/archive/specs/USER_MESSAGE_AND_PROCESSING_JOURNAL_SPEC_2026-03-24.md` — implemented 2026-03-24
- `docs/archive/specs/DOCUMENT_ENTITY_ROUNDTRIP_REFACTOR_SPEC_2026-03-21.md`
- `docs/archive/specs/DOCUMENT_ENTITY_ROUNDTRIP_DEVELOPMENT_PLAN_2026-03-21.md`
- `docs/archive/specs/decomposition.md`
- `docs/archive/specs/IMAGE_UI_PIPELINE_MODES.md`
- `docs/archive/specs/IMAGE_PIPELINE_V2_SPEC.md`
- `docs/archive/specs/IMAGE_PIPELINE_REFACTOR_PLAN.md`
- `docs/archive/specs/REFACTORING_STATE_AND_PREPARATION_SPEC.md`
- `docs/archive/specs/CODE_REVIEW_REMEDIATION_SPEC_2026-03-16.md`
- `docs/archive/specs/DOCX_FORMATTING_REGRESSION_FIX_PLAN_2026-03-15.md`
- `docs/archive/specs/DOCX_FORMATTING_RELIABILITY_REFACTOR_SPEC_2026-03-18.md`
- `docs/archive/specs/DOCUMENT_MODULE_DECOMPOSITION_SPEC_2026-03-20.md`
- `docs/archive/specs/EMPTY_RESPONSE_RETRY_SPEC_2026-03-17.md`
- `docs/archive/specs/FORMAT_RESTORATION_OVERHAUL_SPEC_2026-03-20.md`
- `docs/archive/specs/LIETAER_QUALITY_REGRESSIONS_SPEC_2026-03-20.md`
- `docs/archive/specs/PROMPT_SAFETY_HARDENING_SPEC_2026-03-17.md`
- `docs/archive/specs/TEST_REFACTORING_SPEC_2026-03-15.md`
- `docs/archive/specs/TEXT_MODEL_IO_REGRESSION_FIX_SPEC_2026-03-16.md`
- `docs/archive/specs/UI_LIVE_PANEL_REFACTOR_SPEC_2026-03-16.md`
- `docs/archive/specs/Спецификация MVP_ AI-редактор DOCX через Markdown с веб-интерфейсом.md`
- `docs/archive/specs/Спецификация v1_ сохранение и улучшение изображений в DOCX.md`
- `docs/archive/specs/Спецификация разработки_ Level 1 post-check для image semantic-redraw-mode.md`
- `docs/archive/specs/Спецификация follow-up - quality hardening для image pipeline.md`

## Archived Review Snapshots

- `docs/archive/reviews/CODE_REVIEW_REPORT.md`
- `docs/archive/reviews/CODE_REVIEW_REPORT_2026-03-11.md`
- `docs/archive/reviews/CODE_REVIEW_REPORT_2026-03-12.md`

## Archived Drafts And Non-Canonical Product Notes

- `plans/monetization.md`
- `docs/archive/drafts/monetization1.md`
- `docs/archive/drafts/monatization2.md`

Эти документы можно использовать для архитектурного и исторического контекста, но при конфликте приоритет всегда у текущих runtime- и user-facing документов сверху.

Примечание по структуре: archived-материалы вынесены в `docs/archive/` и `plans/`, но каноничность всё равно определяется этим индексом и статусной пометкой в самом документе. Для новых spec-ов и активных планов archive использовать нельзя.
