# Specification Quality Checklist: Нормализация границ абзацев не склеивает абзацы разного кегля

**Purpose**: Validate specification completeness and quality before implementation (spec-only tier)
**Created**: 2026-11-13
**Feature**: [spec.md](../spec.md)

## Content Quality

- [x] No implementation details beyond the repository's evidence contract (`path:line` evidence and the one place
      the rule lives: the blocked reasons of `document/boundaries.evaluate_paragraph_boundary`)
- [x] Focused on user value (the first paragraph of a chapter is no longer glued to its epigraph and dropped from
      the audiobook as a run of notes; displayed quotations, captions and contents lines keep their own paragraph)
- [x] All mandatory sections completed, plus `## Non-goals`, `## Anti-regression`, `## Changelog` (constitution)

## Requirement Completeness

- [x] No [NEEDS CLARIFICATION] markers remain; the owner's hard requirements (no text lost, no rule fitted to one
      book) are stated as FR-001…FR-005 and the Anti-regression section
- [x] Requirements are testable offline (synthetic DOCX and raw paragraphs; corpus measurements by the production
      code on full audiobook preparations, no LLM, no network)
- [x] Every merge across a size change on the corpus is listed and classified; the trade-off (one disputed join
      lost) and the downstream TOC overrun in another module are recorded in Non-goals and Known limit
- [x] No paid run is needed

## Feature Readiness

- [x] All functional requirements have clear acceptance criteria (SC-001…SC-004)
- [x] Constitution VII: the rule reads typography (font size) and the importer's standalone-note-mark form; the
      size tolerance and the mark form are the PDF importer's existing constants, pinned by a test; no word list;
      test texts are invented, none taken from a corpus book
- [x] Constitution VIII: every code claim checked on `main` @ `9b5db10` and on this branch on 2026-11-13; the
      docstring that quotes corpus measurements was measured the same day with the code as left
