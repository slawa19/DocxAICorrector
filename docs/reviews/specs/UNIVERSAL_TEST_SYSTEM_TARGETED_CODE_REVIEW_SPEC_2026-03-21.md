# Universal Test System Targeted Code Review Spec

**Date:** 2026-03-21  
**Status:** active review specification  
**Purpose:** define the scope, questions, and output contract for a targeted review of the universal test system implementation.

---

## 1. Problem

The project now has a materially implemented universal real-document validation system, but its contracts are spread across runner code, registry configuration, tasks, scripts, and multiple docs. A generic “review everything again” pass would be noisy and low-signal.

The review must instead answer a narrower question:

Can the current universal test system be trusted as a maintainable, contract-consistent, pre-manual-testing quality barrier without hidden schema drift, workflow drift, or runner bugs?

---

## 2. Review Scope

This review is intentionally limited to the universal test system surfaces below.

### 2.1. In Scope

1. full-tier runner implementation;
2. manifest and report schema shape;
3. acceptance logic and its declared policy surface;
4. repeat/soak orchestration and aggregate artifact semantics;
5. latest-alias artifact behavior;
6. visible VS Code task workflow contract for final verification;
7. registry-driven document and run profile integration;
8. deterministic structural-tier schema alignment where it overlaps with full-tier consumers.

### 2.2. Out of Scope

1. unrelated Streamlit UI behavior;
2. general image pipeline internals unless they affect validator contracts directly;
3. broad refactoring proposals outside the test-system boundary;
4. startup performance or lifecycle contracts unrelated to validation;
5. speculative redesign of future acceptance-policy families.

---

## 3. Files And Surfaces To Inspect

Primary code surfaces:

1. `tests/artifacts/real_document_pipeline/run_lietaer_validation.py`
2. `real_document_validation_profiles.py`
3. `real_document_validation_structural.py`
4. `corpus_registry.toml`
5. `.vscode/tasks.json`
6. `scripts/run-real-document-validation.sh`
7. `scripts/run-real-document-quality-gate.sh`
8. `tests/test_real_document_pipeline_validation.py`
9. `tests/test_real_document_validation_profiles.py`

Supporting contract docs:

1. `docs/UNIVERSAL_REAL_DOCUMENT_VALIDATION_SPEC_2026-03-21.md`
2. `docs/WORKFLOW_AND_IMAGE_MODES.md`
3. `docs/testing/UNIVERSAL_TEST_SYSTEM_MAINTENANCE_GUIDE_2026-03-21.md`

---

## 4. Review Questions

The review must explicitly answer these questions.

1. Does the runner produce one stable contract for progress, manifest, report, and latest aliases?
2. Are report and structural-tier schemas aligned enough for maintainable consumers?
3. Is acceptance behavior consistent with what the registry and docs claim?
4. Does repeat/soak aggregation preserve enough child-run detail for debugging intermittent failures?
5. Are latest aliases safe and unambiguous for machines and operators?
6. Does the visible VS Code task workflow actually cover the intended operator use cases?
7. Are there hidden document-specific assumptions left in a supposedly universal system?
8. Are existing tests protecting the most failure-prone contracts?

---

## 5. Review Method

The review should prioritize:

1. bugs;
2. contract ambiguity;
3. schema instability;
4. workflow mismatches;
5. missing tests on high-risk behavior.

The review should not prioritize:

1. style preferences;
2. speculative cleanup;
3. cosmetic naming complaints unless they create operational risk.

---

## 6. Expected Outputs

The review output must contain:

1. findings first, ordered by severity;
2. exact file references for each finding;
3. explanation of impact and likely user or maintainer consequence;
4. open questions or assumptions only after findings;
5. a short summary of residual risk after the findings.

If no bugs are found, the review must still state residual risks and testing gaps explicitly.

---

## 7. What Does Not Change

This review does not itself authorize:

1. broad runner refactoring;
2. schema rewrites across all tiers;
3. removal of compatibility aliases without migration planning;
4. replacing the visible task workflow with agent-only execution.

Any implementation work that crosses those boundaries requires a separate change spec and explicit approval.

---

## 8. Verification Criteria For The Review

The review is considered complete when:

1. the in-scope files have been inspected;
2. the current docs have been compared against the actual implementation;
3. findings are limited to actual current issues, not stale historical remarks;
4. risks are expressed in maintainability and user-visible terms, not only as abstract design preferences.
