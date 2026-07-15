# Feature Specification: Documentation sync to the deterministic importer-first pipeline

Date: 2026-07-15
Status: **PLANNED (Wave 1 / S6).** Documentation accuracy. Remove references to a removed pipeline stage and
nonexistent files, deduplicate the validation workflow, and mark the stale handoff as historical.
Owner surface: `README.md`, `docs/REAL_DOCUMENT_VALIDATION_WORKFLOW.md`,
`docs/testing/REAL_DOCUMENT_VALIDATION_WORKFLOW.md`, `docs/HANDOFF_2026-07-11.md`, and a new internal-link check.
**Explicitly out of scope: the `plans/monetization*.md` drafts** — the three payment/admin variants stay untouched;
that decision is the owner's and comes later.

## Problem (verified against HEAD d27c137)

1. README still documents a REMOVED AI structure-recognition stage and a nonexistent module:
   [README.md:65](/D:/www/Projects/2025/DocxAICorrector/README.md#L65) lists `structure_recognition.py`; prose at
   `:56` and `:90-92` describes the stage. `git ls-files src` contains no `structure_recognition.py`. The current
   workflow doc states the stage was removed:
   [docs/testing/REAL_DOCUMENT_VALIDATION_WORKFLOW.md:17-21](/D:/www/Projects/2025/DocxAICorrector/docs/testing/REAL_DOCUMENT_VALIDATION_WORKFLOW.md#L17-L21)
   ("NOTE (2026-06-22): the AI structure-recognition stage … removed. Preparation is now deterministic").
2. README references specs at paths that now live only under `docs/archive/`:
   [README.md:96](/D:/www/Projects/2025/DocxAICorrector/README.md#L96) → `docs/DOCX_FORMATTING_HARDENING_SPEC_2026-03-13.md`
   (actual: `docs/archive/specs/…`) and `:98` → `docs/UNIVERSAL_REAL_DOCUMENT_VALIDATION_SPEC_2026-03-21.md`
   (actual: `docs/archive/…`).
3. Two `REAL_DOCUMENT_VALIDATION_WORKFLOW.md` exist: the root `docs/` copy is stale (still describes the removed
   "AI-First Structure Recovery Workflow") and has broken markdown fences (unclosed ` ```text ` at L46/L51, double
   close at L53-54). The canonical one is `docs/testing/`.
4. [HANDOFF_2026-07-11.md:29](/D:/www/Projects/2025/DocxAICorrector/docs/HANDOFF_2026-07-11.md#L29) claims specs
   001–012 done and "1966 passed"; specs now run 001–021, spec 012 is still `Status: ACTIVE (cleanup)`, and the
   pytest cache holds 2533 node ids. The counts are stale.
5. README:56 calls the modules "independent" while a real `processing ↔ ui` import cycle exists
   (`processing_service.py:55` ↔ `ui/_app.py:241`).

## Scope (planned)

1. **README pipeline description** rewritten to the current deterministic importer-first pipeline: remove
   `structure_recognition.py` and the AI structure-recognition stage; drop the "independent modules" claim (or
   replace with an accurate coupling note pending the S5 cycle-break).
2. **Fix README spec links** to point at the real `docs/archive/…` locations (or drop them if archival-only).
3. **Single canonical validation workflow:** keep `docs/testing/REAL_DOCUMENT_VALIDATION_WORKFLOW.md`; replace the
   stale root `docs/REAL_DOCUMENT_VALIDATION_WORKFLOW.md` with a short redirect stub pointing at it (removes the
   broken fences and the removed-stage content).
4. **Handoff** marked as a historical snapshot (banner at top), or its resume-point updated; do not keep stale exact
   test counts presented as current.
5. **Internal-link check test:** a static test that every relative Markdown link and repo path mentioned in README
   (and the canonical workflow doc) resolves to an existing file; fails on dangling links. Avoids re-drift.
6. **Do not embed volatile exact test counts** in README (the check/test may assert their absence or tolerate ranges).

## Test plan

- Link-existence test over README + canonical workflow doc: no dangling relative links / repo paths.
- Grep guard: `structure_recognition` does not appear as a live-module reference in README (archive/prompts
  excluded).
- Assert the root workflow file is a short redirect (below a size threshold and containing the redirect marker).

## Out of scope

- `plans/monetization*.md` consolidation and the `monatization2.md` typo — owner decision, deferred.
- Rewriting archived specs under `docs/archive/`.
- The actual `processing ↔ ui` cycle fix (spec S5 / Wave 2); this spec only stops describing the modules as
  independent.

## SaaS rationale

Neutral for SaaS, but a docs baseline that matches the code prevents future backend/spec work from being planned
against a fictional pipeline stage.
