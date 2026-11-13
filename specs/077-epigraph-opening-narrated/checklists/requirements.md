# Specification Quality Checklist: Начало главы, прочитанное как серия из одного примечания, озвучивается

**Purpose**: Validate specification completeness and quality before implementation (spec-only tier)
**Created**: 2026-11-12 (re-checked 2026-11-13 after the move to `main` without spec 076)
**Feature**: [spec.md](../spec.md)

## Content Quality

- [x] No implementation details beyond the repository's evidence contract (`path:line` evidence and the single place
      the rule must live: the audiobook branch of `build_editing_jobs`)
- [x] Focused on user value (the first paragraph of a chapter is read aloud; real one-entry notes stay out)
- [x] All mandatory sections completed, plus `## Non-goals`, `## Anti-regression`, `## Changelog` (constitution)

## Requirement Completeness

- [x] No [NEEDS CLARIFICATION] markers remain; the owner set the constraints (no useful text cut, no per-book fitting,
      narration only) and on 2026-11-13 decided to ship this spec without spec 076
- [x] Requirements are testable offline (synthetic paragraphs in `tests/test_spec_077_epigraph_opening_narrated.py`; the
      corpus measurement uses the production preparation without a model)
- [x] Rejected alternatives recorded in Non-goals (any lead, a lead that is merely not a reference, splitting the
      paragraph, changing the spec 067 mark, a signature that cites a work, a length cap, "no number inside the entry")
- [x] What the listener hears (the glued epigraph, the bare note number) is stated, with what is not verified

## Feature Readiness

- [x] All functional requirements have clear acceptance criteria
- [x] Constitution VII: roles, neighbours and the form of the text only; no word list, no literal from a book; tests use
      invented text
- [x] Constitution VIII: every number measured on 2026-11-13 against the branch code (before and after the rule)
