# Implementation Plan: Stable Source and Preparation Identity

**Branch**: `[045-source-preparation-identity]` | **Date**: 2026-07-20 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/045-source-preparation-identity/spec.md`

## Summary

Extend the persisted-source record so normalized working bytes retain the original PDF/DOC source token and carry an independent payload size/digest. Restore a token-bearing frozen payload only after integrity validation, avoiding reconversion. Add canonical source/target languages to the UI preparation request marker so it agrees with the already language-sensitive prepared-source key.

**Global implementation order**: 044 → 045 → 046 → 048 → 047.

## Technical Context

**Language/Version**: Python 3.13.5 in WSL/Debian

**Primary Dependencies**: Streamlit session state, pathlib/hashlib, existing upload normalization and restart-store modules

**Storage**: Ephemeral `.run/restart_*` and `.run/completed_*` source-cache files plus session metadata

**Testing**: pytest via canonical `scripts/test.sh`; processing-runtime, restart-store, application-flow and restartable UI tests

**Target Platform**: WSL/Debian, Streamlit

**Project Type**: Single Python application

**Performance Goals**: Restored normalized PDF/DOC triggers zero conversion calls; integrity hashing is linear in already-read payload size

**Constraints**: Preserve source-token stability, confined deletion, TTL, native DOCX behavior, and source-cache/output-artifact distinction

**Scale/Scope**: PDF, legacy DOC, native DOCX; restart and completed source records; source/target language marker axes

## Constitution Check

### Pre-design gate

- **I/II — PASS**: runtime and tests use WSL/canonical scripts.
- **III — PASS**: persisted data/UI identity changes follow Spec Kit.
- **V — PASS**: existing source-cache root, cleanup and logs remain; integrity failures use existing observability.
- **VI — PASS**: extend existing payload/record contracts; no cache redesign or duplicate original file.
- **VII — PASS**: identity is content/form metadata, never a document literal.
- **VIII — PASS**: current mismatch is cited and dated 2026-07-20.

### Post-design gate

PASS. The design has one authoritative source token and a separate payload digest, avoiding competing identities. Unverifiable records fail closed as unavailable. No exception required.

## Project Structure

### Documentation (this feature)

```text
specs/045-source-preparation-identity/
├── spec.md
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/persisted-source-contract.md
└── tasks.md
```

### Source Code (repository root)

```text
src/docxaicorrector/
├── processing/
│   ├── processing_runtime.py
│   ├── restart_store.py
│   └── application_flow.py
├── runtime/state.py
└── ui/
    ├── _app.py
    └── application_flow.py

tests/
├── test_processing_runtime.py
├── test_restart_store.py
├── test_application_flow.py
└── test_app_restartable_state.py
```

**Structure Decision**: Persisted record construction/verification stays in restart_store; upload identity stays in processing_runtime; UI flow passes the restored frozen payload without recomputation.

## Complexity Tracking

No constitution violations.
