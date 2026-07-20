# Implementation Plan: Result Delivery Integrity

**Branch**: `[044-result-delivery-integrity]` | **Date**: 2026-07-20 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/044-result-delivery-integrity/spec.md`

## Summary

Reuse the existing marker-free fallback substrate in every controlled fallback branch, then carry an authoritative delivery disposition and notice through the result bundle into the shared UI renderer. Retained blocked bytes remain session-only diagnostic downloads; accepted artifacts and advisory review data retain current semantics.

**Global implementation order**: 044 → 045 → 046 → 048 → 047. This feature lands first and defines the delivery/notice contract later consumed by 047.

## Technical Context

**Language/Version**: Python 3.13.5 in project WSL/Debian runtime

**Primary Dependencies**: Streamlit result UI, existing generation retry/fallback helpers, pipeline late-phase gate, dataclass/mapping result contracts

**Storage**: Streamlit session state and existing `.run/ui_results/` accepted-artifact family; no new persistent store

**Testing**: pytest via `bash scripts/test.sh ...` in WSL; focused generation, late-phase, processing-runtime, and UI selectors

**Target Platform**: WSL/Debian canonical runtime, Streamlit application

**Project Type**: Single Python application with UI and document-processing pipeline

**Performance Goals**: No extra model calls or document rebuilds; result rendering remains constant-time relative to bundle size

**Constraints**: Preserve retry/fallback eligibility, failed terminal outcome, accepted artifact contract, locales, and advisory review-data semantics

**Scale/Scope**: Four controlled fallback outcomes, two UI result entry paths, accepted/warn/blocked delivery states

## Constitution Check

### Pre-design gate

- **I/II Runtime and entry points — PASS**: all proof uses WSL and `scripts/test.sh`; no direct runner is canonical proof.
- **III Spec before code — PASS**: delivery and UI contract changes follow Spec → Plan → Tasks → Implement.
- **IV/VIII Fresh evidence — PASS**: current paths and 2026-07-20 deterministic characterization are recorded in spec.md.
- **V Observability/artifacts — PASS**: accepted artifacts remain `.run/ui_results/*.result.*` with `ui_result_artifacts_saved`; blocked bytes remain diagnostic and non-persisted.
- **VI Minimal scope — PASS**: reuse existing sanitizer and extend the existing result contract; no retry/gate redesign.
- **VII Universal rules — PASS**: marker sanitation keys on the structural marker form; formatting coverage remains review data.

### Post-design gate

PASS. The contract separates delivery disposition from advisory/degradation notices, preventing 047 from overwriting blocked status. No constitution exception or complexity waiver is required.

## Project Structure

### Documentation (this feature)

```text
specs/044-result-delivery-integrity/
├── spec.md
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/result-delivery-contract.md
└── tasks.md
```

### Source Code (repository root)

```text
src/docxaicorrector/
├── generation/_generation.py
├── pipeline/late_phases.py
├── processing/processing_runtime.py
└── ui/
    ├── _app.py
    └── _ui.py

tests/
├── test_generation.py
├── test_late_phases_finalize_gate_persistence.py
├── test_processing_runtime.py
├── test_app_restartable_state.py
└── test_ui.py
```

**Structure Decision**: Keep the existing module boundaries. Generation owns safe fallback text; pipeline owns final disposition; processing owns serialization; UI only renders the contract.

## Complexity Tracking

No constitution violations.
