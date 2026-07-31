# Data Model: Reader Cleanup Production Parity

## EffectiveReaderCleanupSetting

- enabled boolean from supported config/env resolution
- operation
- policy (`off | advisory | strict` as already supported)

Validation: disabled by default; active only for translation and non-off policy.

## FinalEvidenceSet

- final accepted Markdown
- final DOCX bytes
- final run/source-owned diagnostic paths from spec 048
- authoritative acceptance verdict/report

Invariant: all components describe the same final build/run.

## LatePhaseStopState

- existing stop predicate/event
- observed boundary
- terminal stopped outcome

Transition: once observed, no later provider call, rebuild, re-gate, narration group, accepted persistence or success/failure completion begins.

## DegradationNotice

- kind: cleanup or narration
- severity: non-blocking advisory
- safe user message and diagnostic context

Relationship: zero-to-many notices coexist with one spec-044 delivery disposition.

## FinalNarrationSource

- final accepted cleanup lineage
- structurally narration-eligible ordered content
- projection status: mapped or ambiguous

Transition: mapped → narration processing; ambiguous → no narration artifact + advisory. Standalone audiobook never enters this model.
