# Specification Quality Checklist: Висячий отступ примечания не рвёт примечание

**Purpose**: Validate specification completeness and quality before implementation (spec-only tier)
**Created**: 2026-11-12
**Feature**: [spec.md](../spec.md)

## Content Quality

- [x] No implementation details beyond the repository's evidence contract (`path:line` evidence and the one
      place the rule must live: the first-line-indent branch of the PDF import's line grouping)
- [x] Focused on user value (the tail of a note is no longer read aloud as running text in the audiobook, and is
      no longer translated as a paragraph of the body)
- [x] All mandatory sections completed, plus `## Non-goals`, `## Anti-regression`, `## Changelog` (constitution)

## Requirement Completeness

- [x] No [NEEDS CLARIFICATION] markers remain; the owner's two hard requirements (no text lost, no rule fitted to
      one book) are stated as FR-002 and the Anti-regression section
- [x] Requirements are testable offline (synthetic spans; corpus measurements by the production code on cached
      pdfminer spans and full preparations, no LLM, no network)
- [x] Rejected alternatives recorded in Non-goals (R1, the "head is open" and "hangs" conditions, alignment with
      the text after the number, "smaller than the body")
- [x] No paid run is needed

## Feature Readiness

- [x] All functional requirements have clear acceptance criteria (SC-001…SC-005)
- [x] Constitution VII: the rule reads geometry (indent, line fill, size) and the spec 068 note-number form; no
      word list, no number taken from one book — the indent step and the full-line share are the importer's
      existing quantities
- [x] Constitution VIII: every code claim checked on `main` @ `e6a411c` on 2026-11-12; the two docstrings that
      quote corpus measurements touched by this change were re-measured the same day
