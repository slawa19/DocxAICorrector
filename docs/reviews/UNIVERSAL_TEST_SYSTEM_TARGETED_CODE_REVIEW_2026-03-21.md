# Universal Test System Targeted Code Review

**Date:** 2026-03-21  
**Scope spec:** `docs/reviews/specs/UNIVERSAL_TEST_SYSTEM_TARGETED_CODE_REVIEW_SPEC_2026-03-21.md`  
**Focus:** runner, manifest/report schema, acceptance logic, repeat/soak orchestration, artifact aliasing, visible test workflow contract.

---

## Findings

Update after remediation pass on 2026-03-21:

1. the three findings below have been addressed in the current branch;
2. they are retained here as the rationale for the remediation work and as historical review context rather than as still-open defects.

### P1. `latest_manifest_json` changes schema mid-run and serves two incompatible contracts

Relevant code writes two different payload shapes to the same path.

Current behavior:

1. `ValidationProgressTracker._write_locked()` writes a progress-style manifest payload to `latest_manifest_path` during execution;
2. `_write_latest_alias_artifacts()` later overwrites that same path with a much smaller alias-manifest payload after completion.

Impact:

1. any consumer polling `*_latest.json` during execution and after completion sees incompatible schemas at the same path;
2. this makes machine consumers fragile and encourages ad-hoc fallback parsing;
3. the maintenance guide can document the artifact, but the implementation still violates a single stable-contract expectation.

Files:

1. `tests/artifacts/real_document_pipeline/run_lietaer_validation.py`

Severity rationale:

1. this is a real contract ambiguity in a core artifact path, not only naming debt.

### P2. The universal system still lacks a first-class visible task path for arbitrary registered profiles

The implementation is registry-driven, but the operator-facing visible workflow remains effectively fixed to the canonical Lietaer runner and quality gate.

Current behavior:

1. `.vscode/tasks.json` exposes `Run Lietaer Real Validation` and `Run Real Document Quality Gate`;
2. `scripts/run-real-document-validation.sh` always executes the runner without a visible task-level selector for a different document profile;
3. the runner itself supports `DOCXAI_REAL_DOCUMENT_PROFILE`, but the visible task surface does not present that as a first-class supported path.

Impact:

1. maintainers can add profiles to `corpus_registry.toml`, but cannot run them through an equally official visible VS Code task contract;
2. this creates drift between “registry-driven universal system” and “operator-visible supported workflow”; 
3. future AI assistants may fall back to hidden environment-variable launches or ad-hoc terminal commands.

Files:

1. `.vscode/tasks.json`
2. `scripts/run-real-document-validation.sh`
3. `tests/artifacts/real_document_pipeline/run_lietaer_validation.py`

Severity rationale:

1. this is operational contract drift rather than an immediate runtime bug, so it is lower than P1.

### P2. Full-tier reports still carry long-lived duplicate runtime surfaces

Full-tier reports still emit both nested runtime structures and duplicated top-level runtime fields.

Current behavior:

1. top-level `model`, `chunk_size`, `max_retries`, `image_mode`, and `enable_paragraph_markers` are emitted;
2. the same information also exists under `runtime_config.effective` and `runtime_configuration.effective`;
3. structural-tier output already mirrors both runtime keys for compatibility.

Impact:

1. schema consumers have multiple possible sources of truth;
2. future edits can silently desynchronize duplicated fields;
3. documentation can explain the compatibility intent, but the implementation still carries avoidable contract ambiguity.

Files:

1. `tests/artifacts/real_document_pipeline/run_lietaer_validation.py`
2. `real_document_validation_structural.py`

Severity rationale:

1. this is not immediately breaking today, but it is a maintainability risk in the schema layer.

---

## Open Questions

1. Should `*_latest.json` remain a latest-alias manifest only, with progress-state consumers required to read `*_progress.json`, or should the project intentionally keep a richer latest manifest contract?
2. Does the project want a generic visible task such as “Run Real Document Validation Profile” with a prompt for profile id, or should the visible workflow stay intentionally canonical-only plus documented env override?

---

## Residual Risks

Even after the recent hardening pass, the main remaining risks are contract-level rather than algorithmic:

1. artifact-path schema ambiguity;
2. visible-workflow coverage lagging behind registry generalization;
3. duplicate runtime schema surfaces increasing future drift risk.

These are smaller than the already closed normalization and fallback issues, but they are the main current blockers to calling the system fully stable as a reusable maintenance platform.
