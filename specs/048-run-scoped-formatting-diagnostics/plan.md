# Implementation Plan: Run-Scoped Formatting Diagnostics

**Branch**: `[048-run-scoped-formatting-diagnostics]` | **Date**: 2026-07-20 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/048-run-scoped-formatting-diagnostics/spec.md`

## Summary

Propagate existing run and source identities into every live formatting-diagnostics write, embed them in artifact metadata and collision-safe names, and collect by exact ownership rather than mtime. Preserve the shared artifact root, family-wide TTL/count bounds, explicit legacy replay and existing events. This feature must land before 047.

**Global implementation order**: 044 → 045 → 046 → **048 → 047**. Although numbered 048, it precedes 047 so cleanup final-evidence uses ownership from the start and never gains a temporary mtime fallback.

## Technical Context

**Language/Version**: Python 3.13.5 in WSL/Debian

**Primary Dependencies**: pathlib/json, pipeline context, formatting restoration writers, quality gate consumers

**Storage**: `.run/formatting_diagnostics/*.json`, seven-day and 100-artifact family-wide retention

**Testing**: pytest via canonical `scripts/test.sh`; retention, formatting transfer, late phases, quality gate and concurrency tests

**Target Platform**: WSL/Debian application runtime

**Project Type**: Single Python application with concurrent background runs

**Performance Goals**: Exact owned collection without global recursive redesign; preserve default two-worker concurrency

**Constraints**: No global mutable owner, no mtime ownership fallback, no new gate, no retention multiplication, fail-open writes remain observable

**Scale/Scope**: Multiple artifacts per run, same-stage/same-time collisions, two concurrent runs, legacy offline replay

## Constitution Check

### Pre-design gate

- **I/II — PASS**: WSL/canonical commands required.
- **III — PASS**: artifact and cross-module contract uses full Spec Kit sequence.
- **V — PASS**: paths, event identities, retention and replay are explicit.
- **VI — PASS**: only formatting diagnostics and direct consumers change.
- **VII — PASS**: ownership affects evidence provenance, not credit or gate policy; anti-vacuum same-run proof required.
- **VIII — PASS**: current collector/writer/concurrency evidence is dated 2026-07-20.

### Post-design gate

PASS. Exact run+source ownership is threaded through existing call boundaries; no serialization or process-global owner. Review data remains review data. No waiver required.

## Project Structure

### Documentation (this feature)

```text
specs/048-run-scoped-formatting-diagnostics/
├── spec.md
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/diagnostics-ownership-contract.md
└── tasks.md
```

### Source Code (repository root)

```text
src/docxaicorrector/
├── generation/
│   ├── formatting_diagnostics_retention.py
│   └── formatting_transfer.py
├── pipeline/
│   ├── contracts.py
│   ├── support.py
│   ├── _pipeline.py
│   ├── formatting_diagnostics_feedback.py
│   ├── late_phases.py
│   └── quality_gate.py
├── validation/structural.py
└── processing/processing_runtime.py

tests/
├── test_format_restoration.py
├── test_late_phases_finalize_gate_persistence.py
├── test_document_pipeline.py
├── test_structural_validation_characterization.py
├── test_real_document_pipeline_validation.py
└── test_processing_runtime.py
```

**Structure Decision**: Artifact writer/collector owns persistence validation; pipeline passes immutable run/source scope; consumers receive only an owned path list. `pipeline/support.py:132` is a live-run marker writer and receives ownership. `validation/structural.py:268` and the legacy `_pipeline.py:170` compatibility surface are explicit offline/validation-replay paths: they never become automatic live-run collectors and cannot use mtime as ownership.

## Complexity Tracking

No constitution violations.
