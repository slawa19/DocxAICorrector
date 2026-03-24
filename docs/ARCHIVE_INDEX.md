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
- `docs/DOCX_FORMATTING_HARDENING_SPEC_2026-03-13.md`
- `docs/UNIVERSAL_REAL_DOCUMENT_VALIDATION_SPEC_2026-03-21.md`
- `docs/AI_AGENT_DEVELOPMENT_RULES.md`
- `docs/testing/REAL_DOCUMENT_VALIDATION_WORKFLOW.md`
- `docs/testing/UNIVERSAL_TEST_SYSTEM_MAINTENANCE_GUIDE_2026-03-21.md`

## Current Folder Layout

- `docs/` — only top-level canonical repository docs
- `docs/testing/` — active testing and validation maintenance docs
- `docs/reviews/` — review handoffs, review reports, and review specs
- `docs/archive/` — historical, superseded, or realized materials

## Archived Specs And Plans

- `docs/archive/specs/DOCUMENT_ENTITY_ROUNDTRIP_REFACTOR_SPEC_2026-03-21.md`
- `docs/archive/specs/DOCUMENT_ENTITY_ROUNDTRIP_DEVELOPMENT_PLAN_2026-03-21.md`
- `docs/archive/specs/decomposition.md`
- `docs/archive/specs/IMAGE_UI_PIPELINE_MODES.md`
- `docs/archive/specs/IMAGE_PIPELINE_V2_SPEC.md`
- `docs/archive/specs/IMAGE_PIPELINE_REFACTOR_PLAN.md`
- `docs/archive/specs/REFACTORING_STATE_AND_PREPARATION_SPEC.md`
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