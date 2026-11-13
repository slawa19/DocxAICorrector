# Specification Quality Checklist: Первая строка записи списка ссылок с висячим отступом — не заголовок

**Purpose**: Validate specification completeness and quality before implementation (spec-only tier)
**Created**: 2026-11-13
**Feature**: [spec.md](../spec.md)

## Content Quality

- [x] No implementation details beyond the repository's evidence contract (`path:line` evidence and the one
      place the rule must live: the typographic heading path of the PDF import, and why not the form of the
      heading's own text)
- [x] Focused on user value (a reference entry is no longer a heading in the translation, the gate and the
      narration plan; a real sub-heading the same defect erased comes back)
- [x] All mandatory sections completed, plus `## Non-goals`, `## Anti-regression`, `## Changelog` (constitution)

## Requirement Completeness

- [x] The failed checks of the run are quoted verbatim with actual / threshold before any hypothesis (AGENTS.md,
      real-document failure analysis contract)
- [x] No [NEEDS CLARIFICATION] markers remain; the owner's hard requirements (no text lost, no rule fitted to one
      book, no real heading lost) are FR-002, FR-004 and SC-002
- [x] Requirements are testable offline (synthetic spans; corpus measurements by the production code on cached
      pdfminer spans and full preparations, no LLM, no network)
- [x] Rejected alternatives recorded in Non-goals with their measured counts (form of the heading text, a run of
      reference neighbours, the variant without the hanging-indent run, a title lexicon entry)
- [x] No paid run is needed; the gate outcome is traced without a model and its residual risk is named

## Feature Readiness

- [x] All functional requirements have clear acceptance criteria (SC-001…SC-004)
- [x] Constitution VII: the rule reads geometry (indent step, edges repeated in a run, the line running out of room)
      and an invariant the importer already has; no word list, no number taken from one book; test texts invented
- [x] Constitution VIII: every code claim checked on the branch from `main` @ `1712332` on 2026-11-13; the docstring
      that quotes corpus measurements is dated and names the code it was measured on
