# PDF Structural Recovery Remaining Work

Date: 2026-04-27

Parent specs:

- `docs/specs/PDF_SOURCE_IMPORT_SPEC_2026-04-26.md`
- `docs/specs/PDF_TRANSLATION_QUALITY_RECOVERY_SPEC_2026-04-27.md`

## Decision

The next work must stay focused on generic structural recovery for PDF-derived DOCX input.

This document narrows the next implementation pass. It does not invalidate the broader parent recovery spec; it defers domain translation work until structural readiness is observable, safe, and regression-tested.

Do not expand thematic translation profiles, glossary validation, terminology memory, or separate domain-specific quality tracks in this remaining-work pass. The observed failure was caused primarily by broken structure before and during translation:

- TOC/body concatenation;
- isolated bullet and numbered-list fragments;
- weak heading recovery;
- unsafe first-block composition;
- paragraph mapping drift after generation.

For this pass, translation and literary correction remain the responsibility of the existing AI processing pipeline. The recovery layer should only ensure the input and output structure are safe enough for that pipeline.

## Original Task Boundary

`PDF_SOURCE_IMPORT_SPEC_2026-04-26.md` intentionally added PDF only as an input format:

```text
PDF -> LibreOffice DOCX normalization -> existing DOCX pipeline
```

It explicitly avoided a second PDF document model and avoided PDF-specific branches in the core pipeline.

The later quality recovery work is justified only because real LibreOffice-derived DOCX can be structurally unsafe even when conversion succeeds. The right continuation is therefore:

```text
converted DOCX -> generic structure repair/readiness -> existing AI pipeline
```

not:

```text
PDF -> thematic translation profile -> special domain validation
```

The broader future path can still include domain-specific translation quality work after structural readiness is stable:

```text
converted DOCX -> generic structure repair/readiness -> domain-specific translation quality work
```

## What Is Already Done

These changes are useful and should be kept:

- PDF source is registered in corpus as `end-times-pdf-core`.
- Structure validation now runs for both `structure_recognition_mode = "auto"` and `"always"`.
- High-risk/no-op AI can block preparation instead of silently proceeding.
- Background preparation failure now emits controlled terminal runtime events.
- AI structure descriptors now include 600-char previews, previous/next previews, isolated marker flag, TOC candidate flag, and scripture reference flag.
- Deterministic structure repair exists for isolated bullets, numeric markers, bounded TOC, TOC/body boundary, and some heading recovery from TOC.
- Final quality report now records paragraph mapping counts/drift signals, bullet marker headings, and TOC/body concat.
- UI result metadata can include machine-readable quality warnings.
- Real-document structural validation can represent blocked preparation as `preparation_quality_gate_blocked` instead of crashing.

## Overengineering Audit

### Keep

- Generic structural repair and readiness gates.
- Controlled blocked preparation path.
- Machine-readable quality report and artifact warning.
- One real PDF regression entry proving the current state.

### Keep But Do Not Expand Now

- Existing domain config plumbing that passes prepared instructions into processing config.

Reason: it is already implemented and low-risk, but it should not drive the next work.

### Correct Or Constrain

- The current PDF corpus run profile name implies high-quality translation while structural validation uses passthrough.
- `repair_pdf_derived_structure()` currently runs for every extracted DOCX. The implementation is conservative, but this needs native DOCX safety coverage or narrower gating if regressions appear.
- The remaining spec must not add more global sentinels unless diagnostics show they are needed.

## Current Remaining Problems

### P1. Misleading Structural Validation Naming

Current structural corpus validation mutates processing jobs to passthrough. This is valid for structural readiness checks, but it must not look like proof of AI translation quality.

Required changes:

- Rename the PDF structural run profile from `ui-parity-translate-theology-pdf-high-quality` to a generic structural name such as `ui-parity-pdf-structural-recovery`.
- Update `end-times-pdf-core.structural_run_profile` to the new generic profile id.
- If `default_run_profile` is only used as a convenient pointer for this regression, update it too; do not let it imply high-quality AI translation.
- Add explicit result metadata such as `validation_execution_mode = "passthrough"` to structural validation results.
- Keep `validation_tier = "structural"`.
- Remove stale expectations that `end-times-pdf-core` fails on unmapped paragraph thresholds when the current registry expects `preparation_quality_gate_blocked`.

Files to inspect/change:

- `corpus_registry.toml`
- `real_document_validation_structural.py`
- `tests/test_real_document_validation_corpus.py`
- `tests/artifacts/real_document_pipeline/run_lietaer_validation.py`, only if it references the renamed profile or wording

Acceptance:

- Corpus validation output clearly says it is structural passthrough.
- Registry names do not imply high-quality translation for passthrough validation.
- Tests no longer assert that the PDF structural regression uses a theology/high-quality translation profile.

### P1. Preparation Diagnostic Snapshot

Before adding more repair rules, capture why `end-times-pdf-core` is currently blocked.

Add a focused diagnostic helper or test path that prepares only:

```text
tests/sources/Are_We_In_The_End_Times.pdf
```

The snapshot should include:

- paragraph count after extraction;
- heading count;
- TOC header count;
- TOC entry count;
- bounded TOC region count;
- repaired bullet item count;
- repaired numbered item count;
- TOC/body boundary repair count;
- remaining isolated marker count;
- readiness status and reasons;
- quality gate status and reasons;
- AI attempted count or boolean;
- AI classified count;
- AI heading count;
- semantic block count;
- first block target chars;
- first block composition flags: has TOC, has epigraph, has body heading/start, has isolated marker.

Preferred implementation shape:

- Add a small internal helper that builds the snapshot from existing preparation/validation objects and block data.
- Prefer reusing existing metrics functions in `preparation.py`, `structure_validation.py`, `document_structure_repair.py`, and `real_document_validation_structural.py` rather than adding another metrics system.
- The helper may live in the narrowest existing module that already has the needed data; do not create a new subsystem.
- The first test can be synthetic if live PDF setup is too slow, but `end-times-pdf-core` must have a canonical WSL path for real validation.

Files to inspect/change:

- `preparation.py`
- `application_flow.py`, if `PreparedRunContext` needs to expose existing report fields
- `real_document_validation_structural.py`
- `tests/test_preparation.py`
- `tests/test_real_document_validation_corpus.py`

Acceptance:

- Synthetic/unit snapshot tests may assert stable properties.
- The live `end-times-pdf-core` diagnostic is available through the canonical WSL validation path.
- It explains the current blocker without running full AI translation.
- It is machine-readable enough to compare in tests or logs.

### P1. Keep Blocked Or Unblock Deterministically

After the diagnostic snapshot, choose one narrow path.

Path A: keep blocked intentionally.

- Keep `structural_expected_failed_checks = ["preparation_quality_gate_blocked"]`.
- Improve naming and log/UI wording so it is seen as expected structural block, not a crash.
- Do not add more repair rules in the same pass.

Path B: unblock deterministically.

- Fix only the blocker visible in the diagnostic snapshot.
- Re-run `test_corpus_structural_passthrough[end-times-pdf-core]`.
- Update expected failures to the next real structural/output failure, or to pass.

Acceptance:

- The corpus expectation matches the current real state exactly.
- There is no speculative repair rule added without diagnostic evidence.

### P2. First Block Composition Gate

If the diagnostic shows a first semantic block still mixes front matter, TOC, epigraph, and body start, add a small pre-translation gate or splitter.

Recommended minimal behavior:

- Detect a block containing both TOC roles and epigraph/body-start roles.
- In strict translate/readiness mode, block before AI translation.
- If a splitter already exists or can be minimal, split by structural role boundaries; otherwise prefer blocking over risky splitting.

Files to inspect/change:

- `preparation.py`
- semantic block construction helpers used by preparation
- `structure_validation.py`, if the decision belongs in readiness status
- `tests/test_preparation.py`
- `tests/test_structure_validation.py`

Acceptance:

- A block containing TOC plus epigraph/body start is not sent to normal AI translation as one mixed block.
- The rule is based on structural roles and block composition, not PDF filename.

### P2. Shared TOC/Body Concat Detection

The final quality report now detects more TOC/body concat variants than block-level output validation.

Required change:

- Share one helper/pattern between block-level validation and final report validation.
- Cover ASCII dotted leaders, ellipsis, Unicode dotted leaders, middle-dot variants, and whitespace leaders.

Files to inspect/change:

- `document_pipeline_output_validation.py`
- `document_pipeline_late_phases.py`
- `tests/test_document_pipeline.py`
- any existing tests for `classify_processed_block()` or TOC validation

Acceptance:

- Unit tests cover representative mixed leader patterns.
- Block-level and final-report validation do not diverge on the same TOC/body concat example.

### P2. Native DOCX Safety Coverage For Structure Repair

Because structure repair runs for all extracted DOCX, add safety tests before making it more aggressive.

Add native DOCX-like fixtures for:

- a legitimate standalone bullet paragraph that should not become a heading;
- a legitimate standalone number paragraph that should not be merged when the next paragraph is a heading/caption/TOC/table/image boundary;
- front matter that contains short title-like lines but no TOC header;
- body prose that contains dotted text but is not a TOC entry.

Files to inspect/change:

- `tests/test_document_structure_repair.py`
- `document_structure_repair.py`, only if a safety test exposes a false positive
- `document_extraction.py`, only if repair needs to be gated at call site

Acceptance:

- Native DOCX-like fixtures with intentional standalone bullets/numbers/front matter are not incorrectly converted into TOC/headings/lists.
- If a false positive appears, gate aggressive repair steps by measured high-risk signals instead of PDF filename.

## Development Plan For New Session

### Step 0. Baseline Safety

Before editing, inspect current worktree:

```bash
git status --short
git diff --stat
```

Do not revert existing changes unless explicitly requested.

### Step 1. Remove Misleading Structural Profile Naming

Implement:

- Rename `ui-parity-translate-theology-pdf-high-quality` to `ui-parity-pdf-structural-recovery` in `corpus_registry.toml`.
- Update references in tests.
- Add `validation_execution_mode = "passthrough"` to structural validation result payloads.
- Update assertions to check generic structural naming.

Suggested targeted test:

```bash
bash scripts/test.sh tests/test_real_document_validation_corpus.py::test_end_times_pdf_structural_run_profile_uses_theology_full_profile -q
```

This test should be renamed as part of the work, for example:

```text
test_end_times_pdf_structural_run_profile_is_generic_structural_recovery
```

### Step 2. Add Preparation Diagnostic Snapshot

Implement the smallest helper that exposes existing metrics. Avoid new architecture.

Possible result shape:

```python
{
    "paragraph_count": 377,
    "heading_count": 4,
    "toc_header_count": 1,
    "toc_entry_count": 13,
    "bounded_toc_region_count": 1,
    "repaired_bullet_items": 0,
    "repaired_numbered_items": 0,
    "toc_body_boundary_repairs": 1,
    "remaining_isolated_marker_count": 0,
    "readiness_status": "blocked_unsafe_best_effort_only",
    "readiness_reasons": ["heading_count_far_below_toc_expectation"],
    "quality_gate_status": "blocked",
    "quality_gate_reasons": ["structure_readiness_blocked_unsafe_best_effort_only"],
    "structure_ai_attempted": True,
    "ai_classified_count": 0,
    "ai_heading_count": 0,
    "semantic_block_count": 42,
    "first_block_target_chars": 3891,
    "first_block_has_toc": True,
    "first_block_has_epigraph": True,
    "first_block_has_body_start": True,
    "first_block_has_isolated_marker": False,
}
```

The numbers above are illustrative; tests should assert stable properties or use synthetic fixtures unless real-PDF metrics are intentionally locked.

Suggested targeted tests:

```bash
bash scripts/test.sh tests/test_preparation.py -q
bash scripts/test.sh tests/test_real_document_validation_corpus.py::test_corpus_structural_passthrough -vv -x
```

### Step 3. Decide Current State

Use the diagnostic output.

If the PDF is still structurally unsafe:

- keep `preparation_quality_gate_blocked` as expected failure;
- ensure the result says structural block, not crash.

If the PDF is safe after existing repair:

- update expected failure list;
- remove the controlled block expectation for `end-times-pdf-core`;
- run corpus structural passthrough node.

### Step 4. Add Only Evidence-Driven Fixes

Do not implement broad FR-7/FR-8 coverage in one pass.

Allowed examples:

- If first block mixes TOC and body, add first-block composition gate.
- If TOC/body concat detection diverges between block and final validation, share the helper.
- If native DOCX safety tests reveal false positives, narrow the repair guard.

### Step 5. Verify Minimal Test Matrix

Run only tests affected by the change:

```bash
bash scripts/test.sh tests/test_real_document_validation_corpus.py::test_corpus_extraction -vv -x
bash scripts/test.sh tests/test_real_document_validation_corpus.py::test_corpus_structural_passthrough -vv -x
```

Add one or more of these depending on touched files:

```bash
bash scripts/test.sh tests/test_preparation.py -q
bash scripts/test.sh tests/test_structure_validation.py -q
bash scripts/test.sh tests/test_document_structure_repair.py -q
bash scripts/test.sh tests/test_document_pipeline.py -q
```

## Canonical Test Rules

Use the repository canonical WSL entrypoint.

If the agent shell is not WSL, use transport like:

```bash
echo START && wsl.exe -d Debian bash -c "cd /mnt/d/www/projects/2025/DocxAICorrector && bash scripts/test.sh tests/test_file.py -q 2>&1" && echo DONE
```

Do not pass multiple test files to `scripts/test.sh` in one command.

Do not use Windows `.venv` as canonical proof.

Avoid full-suite or real AI translation runs unless explicitly requested.

## Done Criteria For This Remaining Work

This remaining work is complete when:

- PDF structural validation naming is honest and generic;
- structural validation result payloads explicitly say passthrough mode;
- `end-times-pdf-core` has a diagnostic snapshot explaining its current readiness status;
- the corpus either intentionally expects a controlled structural block or passes after a narrow deterministic fix;
- native DOCX safety coverage exists for structure repair behavior that could affect non-PDF documents;
- no new thematic/domain-specific validation track is expanded in this remaining-work pass.
