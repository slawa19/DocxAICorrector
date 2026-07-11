# Feature Specification: Remove legacy/truncated test-source documents and all references

Date: 2026-07-11
Status: ACTIVE (cleanup). Owner-directed 2026-07-11: "удали легаси из всех рантаймов, тестов и документации".
Owner surface: `corpus_registry.toml`, `tests/sources/archive/`, the real-document harness, CI workflows,
`.vscode/tasks.json`, benchmark configs, and docs.
Companion: `docs/specs/GLOBAL_PLAN_2026-06-16.md` (breadth-validation section — RETRACTED, it was run on legacy).
Changelog:
- 2026-07-11 — Created after the owner flagged that the breadth runs used `tests/sources/archive/` samples
  (a 67 KB legacy `.doc`, a 153-paragraph audiobook `.docx` EXCERPT) — truncated/legacy fixtures, not real
  books. Quality/breadth validation must run on the real full books in `tests/sources/book/`. Remove the legacy
  sources and every runtime/test/doc reference so they cannot be picked again.

## Problem

The corpus registry mixes two tiers of source documents under one lookup:
- **Real full books** — `tests/sources/book/*.pdf` (Money, Rethinking Money, The Value of Everything, Creating
  Wealth), profiles `*-pdf-full-*` / `*-pdf-full-heldout`. KEEP.
- **Legacy/truncated samples** — `tests/sources/archive/*` (single chapters, a 20-page slice, a page-region
  slice, an audiobook excerpt, an old `.doc`), profiles `lietaer-core`, `religion-wealth-core`,
  `mazzucato-audiobook-core`, `lietaer-pdf-first-20-benchmark`, `lietaer-pdf-first-20-structure-core`,
  `lietaer-pdf-chapter-region-core`. REMOVE.

Selecting a legacy profile by env var produced an unrepresentative run that was mistakenly reported as breadth
validation. The fix removes the temptation entirely.

## Requirements

- **FR-001**: Remove the six legacy `[[documents]]` blocks from `corpus_registry.toml`; keep the four `book/`
  profiles and all `[[run_profiles]]`.
- **FR-002**: `git rm` all files under `tests/sources/archive/` (including orphans not referenced by any
  profile), and the now-empty archive dir.
- **FR-003**: Change the harness default profile (`run_lietaer_validation.py`, the `DOCXAI_REAL_DOCUMENT_PROFILE`
  default `lietaer-core`, both occurrences) to a real book profile — `lietaer-pdf-full-benchmark`.
- **FR-004**: Delete tests that ONLY exercise a legacy profile: `tests/test_real_document_quality_gate.py`,
  `tests/test_real_document_audiobook_spec.py`, and the function
  `test_reader_cleanup_comparison_only_target_document_is_chapter_region_pdf` in
  `tests/test_real_document_validation_corpus.py`. Keep the auto-parametrized `test_corpus_extraction` /
  `test_corpus_structural_passthrough` (they enumerate the live registry → automatically cover only the 4 real
  books after FR-001).
- **FR-005**: Repoint every runtime reference to a legacy profile to a real book profile, in lockstep with the
  static-contract assertions that check them: `.vscode/tasks.json`, `tests/test_script_contract_static.py`, the
  CI workflows (`real-document-validation.yml`), the benchmark configs/runners, and the `structural.py` argparse
  help example.
- **FR-006**: Delete CI workflows whose only job runs a now-deleted legacy test
  (`real-document-audiobook-sanity.yml`, `real-document-quality-gate.yml`).
- **FR-007**: Remove git-tracked artifacts derived from a legacy profile:
  `tests/artifacts/structural_diagnostics/lietaer-pdf-chapter-region-core/*` and the stray root `test_out.txt`.
- **FR-008**: Update prose docs that name legacy profiles (README, AGENTS.md, copilot-instructions, the two
  REAL_DOCUMENT_VALIDATION_WORKFLOW.md, CHANGELOG, the translation-comparison article) to the real book
  profiles. Leave `docs/archive/**` as historical record.
- **FR-009**: RETRACT the 2026-07-11 breadth-validation result in `GLOBAL_PLAN` (it was run on legacy sources);
  mark breadth as PENDING on real books.

## Non-goals

- **Not recreating the dropped legacy-only coverage** (legacy `.doc` auto-conversion, audiobook postprocess,
  truncated structural-diagnostic) on book profiles — the owner accepts the coverage loss. Real-book corpus
  coverage remains via the auto-parametrized corpus tests.
- **Not editing `docs/archive/**`** — historical snapshots stay as-is.
- **Not touching the four real book profiles or the run profiles.**

## Anti-regression

- **Suite green after removal:** full `bash scripts/test.sh` passes; pyright ratchet ≤ 244. The auto-parametrized
  corpus tests still enumerate the 4 real books (no legacy params remain).
- **No dangling reference:** grep for each legacy profile id and `sources/archive` returns only `docs/archive/**`
  historical mentions after the change.
- **Harness default resolves:** a run with no `DOCXAI_REAL_DOCUMENT_PROFILE` set resolves to a real book profile,
  not a KeyError.
- **Static-contract test passes:** `test_script_contract_static.py` matches the edited configs (lockstep).
