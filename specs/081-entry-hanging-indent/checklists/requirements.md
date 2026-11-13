# Specification Quality Checklist: Висячий отступ записи списка литературы не рвёт запись

**Purpose**: Validate specification completeness and quality before implementation (spec-only tier)
**Created**: 2026-11-13
**Feature**: [spec.md](../spec.md)

## Content Quality

- [x] No implementation details beyond the repository's evidence contract (`path:line` evidence and the one
      place the rule must live: the notes / reference join of spec 064 R-7, and why not the line grouping)
- [x] Focused on user value (a wrapped line of a reference entry is no longer a paragraph of its own in the
      translation and the result DOCX)
- [x] All mandatory sections completed, plus `## Non-goals`, `## Anti-regression`, `## Changelog` (constitution)

## Requirement Completeness

- [x] No [NEEDS CLARIFICATION] markers remain; the owner's hard requirements (no text lost, no rule fitted to one
      book, no wrong join) are FR-002, FR-003 and the measured zero of the Changelog
- [x] Requirements are testable offline (synthetic spans; corpus measurements by the production code on cached
      pdfminer spans and full preparations, no LLM, no network)
- [x] Rejected alternatives recorded in Non-goals (R1 in the line grouping with or without a run condition; the
      torn entries the rule sees and refuses)
- [x] No paid run is needed

## Feature Readiness

- [x] All functional requirements have clear acceptance criteria (SC-001…SC-006)
- [x] Constitution VII: the rule reads geometry (indent step, edges repeated in a run, size, blank lines) and keeps
      the join's explicit entry markers; no word list, no number taken from one book; test texts are invented
- [x] Constitution VIII: every code claim checked on the branch from `main` @ `9b5db10` on 2026-11-13; the R-7
      block comment that quotes corpus measurements was re-measured and dated the same day
