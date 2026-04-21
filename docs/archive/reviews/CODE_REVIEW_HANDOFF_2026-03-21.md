# Code Review Handoff

**Date:** 2026-03-21  
**Scope:** universal real-document validation architecture, legacy `.doc` normalization, repeat/soak execution, and regression hardening around `heading_only_output`

## 1. Outcome

This change set completes the main implementation path from `docs/UNIVERSAL_REAL_DOCUMENT_VALIDATION_SPEC_2026-03-21.md` and adds one important runtime extension that was not purely validator-local: project-level legacy `.doc` auto-conversion.

The system now has:

1. registry-driven real-document profiles;
2. independent run profiles;
3. deterministic `extraction` and `structural` corpus tiers;
4. full-tier UI-parity validation with repeat/soak aggregation;
5. project-level normalization of `.docx` and legacy `.doc` uploads into a single downstream DOCX contract;
6. explicit regression coverage for `heading_only_output` in both pipeline behavior and real-document failure classification.

## 2. Architecture Delta

### 2.1. New input boundary

The most important architectural change outside the validator itself is the new normalization boundary in `processing_runtime.py`.

Before:

1. several flows still assumed DOCX-only input;
2. the second real corpus document had to exist as a pre-normalized sibling `.docx` to participate in automated validation;
3. UI path and corpus-validation path could drift on how source bytes were interpreted.

After:

1. upload format is detected once, near payload freezing and token construction;
2. legacy `.doc` is converted to a working `.docx` through either `soffice` or `antiword + pandoc`;
3. all downstream flows consume normalized DOCX bytes;
4. tokenization, preparation, extraction, structural validation, and full validator now agree on the same source contract.

### 2.2. Real-document validation generalized

The validator is no longer effectively tied to one hard-coded source file.

Current shape:

1. `corpus_registry.toml` declares documents and run profiles;
2. `real_document_validation_profiles.py` resolves document/run profile contracts and runtime overrides;
3. `real_document_validation_structural.py` provides deterministic corpus-backed tiers;
4. `tests/artifacts/real_document_pipeline/run_lietaer_validation.py` remains the canonical full-tier runner, but now behaves as a profile-driven replay harness.

### 2.3. Mixed corpus is now real, not theoretical

The second corpus document `religion-wealth-core` now points to the original legacy `.doc` source rather than to a manually normalized sibling `.docx`.

That matters because it exercises:

1. document profile resolution;
2. runtime normalization;
3. deterministic structural validation;
4. full-tier replay path;
5. report generation against a mixed-format corpus.

## 3. Main Files To Review

### Input normalization and runtime boundary

1. `processing_runtime.py`
2. `application_flow.py`
3. `document.py`

Review focus:

1. format detection by magic bytes and extension fallback;
2. backend selection order: `soffice` first, `antiword + pandoc` second;
3. whether normalized filename and normalized bytes are applied consistently before token creation and validation;
4. whether errors for unavailable conversion backends are explicit and user-facing enough.

### Real-document validation platform

1. `corpus_registry.toml`
2. `real_document_validation_profiles.py`
3. `real_document_validation_structural.py`
4. `tests/artifacts/real_document_pipeline/run_lietaer_validation.py`

Review focus:

1. profile separation between document identity and run configuration;
2. reuse of normalized DOCX contract inside deterministic and full tiers;
3. repeat/soak aggregation behavior and failure classification propagation;
4. whether report payloads and profile metadata still match repository expectations.

### Regression and behavior coverage

1. `tests/test_document_pipeline.py`
2. `tests/test_real_document_pipeline_validation.py`
3. `tests/test_processing_runtime.py`
4. `tests/test_application_flow.py`
5. `tests/test_document.py`

Review focus:

1. `heading_only_output` coverage is now present at both pipeline behavior and report classification levels;
2. legacy `.doc` normalization is covered at runtime, application-flow, and document-read boundaries;
3. tests do not silently depend on real system converters when they are meant to be unit-level.

## 4. Verification Performed

Visible verification path used:

1. VS Code task `Run Full Pytest`

Observed result:

1. `450 passed, 5 skipped`

## 5. Known Limitations

These are known and intentional at the end of this change set.

1. `religion-wealth-core` remains `tolerant` in deterministic structural mode.
2. The remaining tolerance is tied to one bounded page-separator-like formatting diagnostic, not to generalized text loss.
3. Legacy `.doc` support depends on external WSL tools and will fail explicitly if neither backend is installed.
4. The full-tier runner still uses the historical `run_lietaer_validation.py` filename even though its behavior is now generic and profile-driven.

## 6. Suggested Review Order

1. `processing_runtime.py`
2. `application_flow.py`
3. `document.py`
4. `corpus_registry.toml`
5. `real_document_validation_structural.py`
6. `tests/artifacts/real_document_pipeline/run_lietaer_validation.py`
7. test files
8. docs

This order makes it easier to validate the boundary change first, then inspect how the validator reuses that contract.

## 7. Questions Worth Asking During Review

1. Should the generic full-tier runner be renamed in a future follow-up so its filename no longer implies a single-document scope?
2. Should conversion backend details be written into the full validation report manifest in a richer form than the current source-path and normalized-runtime behavior?
3. Is the remaining tolerant structural profile acceptable as a documented temporary state, or should strictness for `religion-wealth-core` be treated as the next hardening task?