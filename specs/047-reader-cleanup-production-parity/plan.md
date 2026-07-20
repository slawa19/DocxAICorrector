# Implementation Plan: Reader Cleanup Production Parity

**Branch**: `[047-reader-cleanup-production-parity]` | **Date**: 2026-07-20 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/047-reader-cleanup-production-parity/spec.md`

## Summary

Map the existing disabled-by-default configuration into the UI translation pipeline, then make late phases cancellable and evidence-coherent. Final acceptance consumes spec-048 owned diagnostics, advisory cleanup/narration notices coexist with spec-044 delivery disposition, and additive translation narration is projected from final accepted cleanup lineage. Standalone audiobook remains untouched.

**Global implementation order**: 044 → 045 → 046 → **048 → 047**. Spec 048 is a hard prerequisite for 047 final-diagnostics tasks; no interim mtime implementation is allowed.

## Technical Context

**Language/Version**: Python 3.13.5 in WSL/Debian

**Primary Dependencies**: Streamlit UI config, existing reader-cleanup service, pipeline late phases, narration postprocess, spec-044 delivery notices, spec-048 diagnostics ownership

**Storage**: Existing result/session state, `.run/ui_results/` accepted artifacts, owned formatting diagnostics and current reports

**Testing**: pytest via `scripts/test.sh`; config/UI flow, reader cleanup, narration, late-phase/persistence and document-pipeline tests

**Target Platform**: WSL/Debian Streamlit application

**Project Type**: Single Python application with background processing

**Performance Goals**: Disabled runs retain current single-build/no-cleanup cost; stop prevents all work after next safe boundary

**Constraints**: Disabled by default; translation only; no forced cancellation of in-flight calls; standalone audiobook unchanged; formatting coverage remains review data

**Scale/Scope**: UI translation path, cleanup changed/no-op/advisory outcomes, late stop boundaries, additive translation narration

## Constitution Check

### Pre-design gate

- **I/II — PASS**: WSL/canonical verification only.
- **III — PASS**: cross-module UI/pipeline/artifact behavior uses full Spec Kit.
- **V — PASS**: final report authority, owned diagnostic paths, events and accepted artifacts are explicit.
- **VI — PASS**: reuses current cleanup/narration services; no prompt/classifier redesign.
- **VII — PASS**: narration eligibility uses existing role/form/lineage; ambiguity omits narration rather than guesses; review data is not gated.
- **VIII — PASS**: F4/F7/F8/F9 and narration provenance are dated 2026-07-20 with focused tests.

### Post-design gate

PASS conditional on completed spec 044 and 048 contracts. The dependency removes competing notice fields and mtime diagnostics. Standalone audiobook is explicitly outside all changed transitions.

## Project Structure

### Documentation (this feature)

```text
specs/047-reader-cleanup-production-parity/
├── spec.md
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/reader-cleanup-finalization-contract.md
└── tasks.md
```

### Source Code (repository root)

```text
src/docxaicorrector/
├── core/config_runtime_sections.py
├── ui/
│   ├── _app.py
│   └── locales/{en,ru}.json
├── pipeline/
│   ├── contracts.py
│   ├── late_phases.py
│   ├── reader_cleanup_rebuild.py
│   ├── reader_cleanup_postprocess.py
│   └── narration_postprocess.py
└── reader_cleanup_mvp/

tests/
├── test_config.py
├── test_app_preparation.py
├── test_document_pipeline.py
├── test_late_phases_finalize_gate_persistence.py
├── test_reader_cleanup_mvp.py
└── test_ui.py
```

**Structure Decision**: UI resolves effective config; late_phases orchestrates cancellation/evidence/notices; cleanup and narration helpers expose bounded stop callbacks and lineage projection without taking delivery authority.

## Complexity Tracking

No constitution violations. Cross-feature prerequisites are intentional contract reuse, not new architecture.
