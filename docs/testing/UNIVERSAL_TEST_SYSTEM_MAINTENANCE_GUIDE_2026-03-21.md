# Universal Test System Maintenance Guide

**Date:** 2026-03-21  
**Status:** active maintenance guide  
**Purpose:** canonical working document for maintaining the universal real-document and UI-pipeline-oriented test system.

---

## 1. Scope

This guide defines how the project maintains and extends the universal test system that is intended to catch UI-pipeline regressions before user-facing manual testing.

This document complements, but does not replace:

1. `docs/UNIVERSAL_REAL_DOCUMENT_VALIDATION_SPEC_2026-03-21.md` for architecture and implementation status;
2. `docs/WORKFLOW_AND_IMAGE_MODES.md` for workflow and runtime source-of-truth contracts;
3. `.github/copilot-instructions.md` for AI-agent workflow and visible test execution rules.

If these documents disagree:

1. visible VS Code task execution contract follows `.github/copilot-instructions.md` and `docs/WORKFLOW_AND_IMAGE_MODES.md`;
2. runtime and artifact architecture follows `docs/UNIVERSAL_REAL_DOCUMENT_VALIDATION_SPEC_2026-03-21.md`;
3. this document defines maintenance procedure and extension rules for the test system.

---

## 2. Test Tier Roles

The universal system has five operational layers. They are not interchangeable.

### 2.1. Deterministic Extraction Tier

Purpose:

1. verify that a registered source document is extractable after normalization;
2. verify minimum structural expectations such as paragraph count, headings, images, tables, and numbered lists;
3. stay cheap and deterministic enough for routine regression use.

Must not:

1. call the model;
2. claim UI parity;
3. be used as proof that the semantic pipeline is safe.

### 2.2. Deterministic Structural Tier

Purpose:

1. run the real normalization, preparation, passthrough assembly, formatting restoration, and DOCX post-processing path;
2. validate structural preservation signals without model nondeterminism;
3. catch formatting-transfer regressions before full-tier validation.

Must validate at least:

1. output DOCX opens;
2. formatting diagnostics thresholds;
3. unmapped paragraph thresholds;
4. heading drift thresholds;
5. non-empty output and no heading-only collapse where required.

### 2.3. Full-Tier Validation

Purpose:

1. exercise the same practical pipeline shape as the UI path;
2. catch model-output and runtime-combination failures not visible in deterministic tiers;
3. produce run-scoped artifacts suitable for failure analysis and replay.

This is the main pre-manual-testing quality barrier.

### 2.4. Repeat/Soak Validation

Purpose:

1. detect intermittent failures that a single model-backed run can miss;
2. aggregate child-run outcomes into one parent report;
3. identify representative failure and success artifacts.

This tier exists because single-run success is not enough evidence for UI safety.

### 2.5. Quality Gate

Purpose:

1. provide an explicit, operator-visible high-signal gate for canonical real-document validation;
2. act as the final heavy validation path when stronger confidence is required;
3. remain separate from ordinary fast pytest usage.

Quality gate runs must stay intentionally selective and visible.

---

## 3. Canonical Execution Contract

Final user-facing verification must use visible VS Code tasks.

Approved visible task paths:

1. `Run Full Pytest`
2. `Run Current Test File`
3. `Run Current Test Node`
4. `Run Lietaer Real Validation`
5. `Run Real Document Validation Profile`
6. `Run Real Document Quality Gate`

Rules:

1. agent-side hidden shell output is not final proof;
2. background pytest verification is forbidden as a final claim of success;
3. one selector per debug command when ad-hoc debugging is necessary;
4. if no existing task matches the requested visible scope, that limitation must be stated explicitly rather than silently replaced by hidden execution.

Canonical entry points behind the tasks:

1. `bash scripts/test.sh ...`
2. `bash scripts/run-real-document-validation.sh`
3. `bash scripts/run-real-document-quality-gate.sh`

---

## 4. Required Artifact Contract

Every full-tier run must produce run-scoped artifacts under:

1. `tests/artifacts/real_document_pipeline/runs/<run_id>/`

Required artifacts for a single full-tier run:

1. report JSON;
2. summary TXT;
3. progress JSON;
4. output markdown when markdown exists;
5. output DOCX when DOCX exists.

Required latest aliases at artifact root:

1. latest report JSON;
2. latest summary TXT;
3. latest progress JSON;
4. latest markdown alias when markdown exists;
5. latest DOCX alias when DOCX exists;
6. latest manifest JSON.

Latest manifest JSON must keep one stable schema throughout the run lifecycle. It must not expose one payload shape while the run is active and a different payload shape after completion.

Required report areas:

1. run metadata;
2. source file reference;
3. result and failure classification;
4. runtime configuration;
5. preparation payload;
6. runtime snapshot and event tails;
7. acceptance result with failed checks;
8. output artifact references;
9. formatting diagnostics references and payloads.

Repeat/soak parent report must additionally include:

1. repeat summary;
2. child run list;
3. explicit first failing child artifact references when failures exist;
4. explicit representative successful child artifact references when successes exist.

Maintenance rule:

1. do not change artifact names, keys, or required sections casually;
2. if a schema change is intentional, update code, tests, and this guide together;
3. additive compatibility aliases are acceptable during transitions, but long-lived duplicate schema fields should be treated as debt and reviewed explicitly.

---

## 5. Adding a New Document Profile

New profiles must be added through `corpus_registry.toml` rather than hard-coded runner edits.

Required steps:

1. add a new `[[documents]]` entry;
2. set `id`, `source_path`, `artifact_prefix`, and `provenance`;
3. declare structural expectations such as paragraphs, headings, images, tables, and numbering;
4. declare `default_run_profile`;
5. declare `expected_acceptance_policy` using a currently supported value;
6. declare tags describing why the document exists in the corpus.

If the profile is tolerant rather than strict:

1. provide explicit bounded tolerances;
2. provide `tolerance_reason`;
3. document why promotion to strict is not yet possible.

When a new profile is added, corresponding work must include:

1. at least extraction-tier coverage;
2. structural-tier coverage if the document is intended for routine corpus validation;
3. visible validation path documentation if the profile is intended for operators, not only for internal research.

Maintenance rule:

1. adding a profile is not complete until the expected checks and artifact expectations are recorded.

---

## 6. Updating Acceptance Checks

Acceptance checks are part of the quality contract, not a convenience layer.

Allowed changes:

1. adding a new check that catches a real user-visible failure mode;
2. tightening an existing check when real artifacts prove the previous threshold was too weak;
3. moving a check between tiers when its correct tier is clearer after investigation;
4. adding compatibility aliases when normalizing report schema.

Disallowed changes without explicit decision and documentation update:

1. weakening thresholds because the current implementation fails them;
2. removing a check only to make tests green;
3. converting strict checks to tolerant behavior silently;
4. changing the meaning of a report field without updating consumers and docs.

If a check must be relaxed:

1. record the reason;
2. document the bounded tolerance;
3. add or update tests that prove the new rule is intentional rather than accidental.

---

## 7. How AI Assistants Must Extend The Test System

When an AI assistant changes or extends this test system, the required order is:

1. contract first;
2. targeted tests second;
3. visible verification third.

Concrete workflow:

1. inspect existing docs, registry, tasks, and affected code paths;
2. identify whether the change is contract, schema, profile, or runner behavior;
3. update the active spec or maintenance docs before broadening architecture or changing public test contracts;
4. add focused regression tests for the precise behavior being changed;
5. run the final verification in visible VS Code tasks whenever the requested scope has a matching task;
6. report remaining risks explicitly rather than overstating confidence.

AI assistants must not:

1. silently invent a second workflow for running tests;
2. replace visible verification with hidden terminal output;
3. add thin tests that only mirror implementation wiring without protecting user-visible outcomes;
4. broaden the system into a large refactor without a written specification.

---

## 8. Stop Criteria

Hardening is complete enough for the current iteration when:

1. contracts are documented and consistent;
2. runner, registry, report schema, and artifact expectations are stable enough for routine use;
3. key known failure modes have targeted regression coverage;
4. visible verification paths exist for routine operator use;
5. remaining gaps are clearly documented as bounded follow-up work.

Work becomes overengineering when it starts doing one or more of these:

1. decomposing the runner into many modules without a concrete contract benefit;
2. redesigning all report schemas at once without a consumer-driven need;
3. generalizing undeployed acceptance-policy variants before a real second policy exists;
4. replacing compatibility naming or alias layers before the operational migration plan exists;
5. writing speculative abstraction for profile classes or runner orchestration without a real second implementation path.

Rule of thumb:

1. fix contract drift, artifact ambiguity, missing tests, and visible workflow gaps;
2. stop before speculative platform refactoring.

---

## 9. Maintenance Checklist

Before claiming the universal test system has been safely updated, confirm:

1. docs reflect the intended contract;
2. registry changes are explicit and bounded;
3. artifact schema changes are tested;
4. acceptance changes are justified and not weakened accidentally;
5. final verification path is visible to the user;
6. remaining risks are documented.
