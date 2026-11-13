# Specification Quality Checklist: Серия примечаний цитирует — нумерованный текст тела не читается как примечания

**Purpose**: Validate specification completeness and quality before implementation (spec-only tier)
**Created**: 2026-11-13
**Feature**: [spec.md](../spec.md)

## Content Quality

- [x] No implementation details beyond the repository's evidence contract (`path:line` evidence and the single place
      the rule must live: the spec 067 form in `output_validation._notes_run_numbered_parts`)
- [x] Focused on user value (numbered body text is narrated and translated as body; real notes stay notes)
- [x] All mandatory sections completed, plus `## Non-goals`, `## Anti-regression`, `## Changelog` (constitution)

## Requirement Completeness

- [x] No [NEEDS CLARIFICATION] markers remain; the owner's constraints (no useful text cut, no per-book fitting, measure
      the translation side) are met by measurement
- [x] Requirements are testable offline (synthetic paragraphs in `tests/test_spec_079_notes_run_must_cite.py`; the
      corpus measurement uses the production preparation without a model)
- [x] Every candidate direction from the brief measured and either chosen or rejected with what it loses (R1–R7)
- [x] The residual (very short steps around an italic span, a step that is itself a reference) and the cost (a run of
      commentary only) are named

## Feature Readiness

- [x] All functional requirements have clear acceptance criteria
- [x] Constitution VII: an existing per-piece test, no new threshold, no word list, no literal from a book; tests use
      invented text
- [x] Constitution VIII: every number measured on 2026-11-13 against the branch code (before and after the rule)
