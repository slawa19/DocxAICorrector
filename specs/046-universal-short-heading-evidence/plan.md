# Implementation Plan: Universal Short-Heading Evidence

**Branch**: `[046-universal-short-heading-evidence]` | **Date**: 2026-07-20 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/046-universal-short-heading-evidence/spec.md`

## Summary

Remove the length-only promotion/hint branch while retaining explicit heading semantics, existing universal typography evidence, and authoritative non-heading classifications. Replace the old positive expectation with paired body/real-heading counter-proofs in both recovery modes.

**Global implementation order**: 044 → 045 → 046 → 048 → 047.

## Technical Context

**Language/Version**: Python 3.13.5 in WSL/Debian

**Primary Dependencies**: python-docx extraction metadata and existing deterministic role helpers

**Storage**: N/A; in-memory paragraph metadata only

**Testing**: pytest via `scripts/test.sh`, focused document extraction/role/preparation tests

**Target Platform**: WSL/Debian pipeline runtime

**Project Type**: Single Python document-processing application

**Performance Goals**: No additional external calls and no measurable preparation overhead

**Constraints**: Constitution VII no-source-signal/no-repair; no book/language literals; preserve importer-first architecture

**Scale/Scope**: One unsafe shortcut and its direct expectations; legacy and AI-first recovery settings

## Constitution Check

### Pre-design gate

- **I/II — PASS**: WSL and canonical test entry point specified.
- **III — PASS**: structure-recognition behavior is specified before code.
- **IV/VIII — PASS**: no stale real-document claim; current deterministic test passed 2026-07-20.
- **V — PASS**: no new artifacts/logs.
- **VI — PASS**: remove one branch; no classifier redesign.
- **VII — PASS**: explicitly enforces form/role evidence and paired anti-vacuum tests.

### Post-design gate

PASS. No signal is accepted rather than guessed. The form-evidence positive and matched no-form negative prevent both false promotion and vacuum demotion.

## Project Structure

### Documentation (this feature)

```text
specs/046-universal-short-heading-evidence/
├── spec.md
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/heading-evidence-contract.md
└── tasks.md
```

### Source Code (repository root)

```text
src/docxaicorrector/document/
├── roles.py
└── extraction.py

tests/
└── test_document_extraction.py
```

**Structure Decision**: Keep classification in document/roles.py and verify it through the normal extraction boundary; downstream assembly is untouched.

## Complexity Tracking

No constitution violations.
