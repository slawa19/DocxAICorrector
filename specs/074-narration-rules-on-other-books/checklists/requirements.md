# Specification Quality Checklist: Правила озвучки, проверенные на книгах других авторов

**Purpose**: Validate specification completeness and quality before implementation (spec-only tier)
**Created**: 2026-11-11 (re-checked 2026-11-11 after the Codex spec review and the owner decisions)
**Feature**: [spec.md](../spec.md)

## Content Quality

- [x] No implementation details beyond the repository's evidence contract (function names are `path:line` evidence and
      the single places a rule must live: `build_narration_document_plan`, `parse_reading_glossary_response`,
      `narration_residue._URL_OR_DOMAIN`, the audiobook prompts)
- [x] Focused on user value (the book divides so that Studio accepts it, abbreviations are read by one convention, a web
      address is heard as a short domain)
- [x] Written for non-technical stakeholders in the user stories and success criteria
- [x] All mandatory sections completed, plus `## Non-goals`, `## Anti-regression`, `## Changelog` (constitution)

## Requirement Completeness

- [x] No [NEEDS CLARIFICATION] markers remain; one owner question (В-1, source-side address shortening) with a
      recommendation; it does not block the FRs as written
- [x] Requirements are testable and unambiguous (each FR has an offline replay or synthetic criterion)
- [x] Success criteria are measurable (chapter counts, glossary entries rewritten, addresses per book)
- [x] Every rule measured on ALL available documents, including those without the defect (15 documents, 6 glossaries /
      358 entries, 7 translated documents for addresses), plus a synthetic structure matrix whose answers are written
      in the spec before implementation
- [x] Each rule's known cost is stated (uneven books, heading-only chapters, books without inner boundaries, VW/KfW,
      trailing superscript in an IRI path, the form check cannot see a spoken path)
- [x] Withdrawn rules (FR-201, FR-202, FR-301, the "half" threshold, the rejection branch of FR-303) are recorded with the
      counterexample that withdrew them
- [x] Paid verification is a step that needs owner consent, with a cost estimate (CW ≈ 0,47 $ only)

## Feature Readiness

- [x] All functional requirements have clear acceptance criteria
- [x] Constitution VII: no word lists or per-book literals in rules or tests; alphabet letter-name tables argued (and
      confirmed by Codex) as a property of the script; no domain-zone table in code (FR-404)
- [x] Constitution VIII: every claim of a live defect is measured on `main` @ `fab2b79` on 2026-11-11

## Notes

- Spec-only tier (Constitution III): defect-driven remediation; no `plan.md`/`tasks.md`.
