# Research: Result Delivery Integrity

## Decision 1: One sanitizer substrate for all controlled fallbacks

**Decision**: Return the already-derived marker-free source substrate in all four eligible marker-mode fallbacks.

**Rationale**: The adjacent validation fallback proves the intended behavior and avoids a second parser.

**Alternatives considered**: Sanitize at DOCX assembly (too late); remove markers from model requests (breaks control protocol); broad regex at UI (wrong layer).

## Decision 2: Delivery disposition is authoritative

**Decision**: Carry accepted/warn/blocked disposition plus explanation through the result bundle. Bytes alone never imply acceptance.

**Rationale**: The final gate already decides deliverability; serialization currently loses that fact.

**Alternatives considered**: Infer from terminal outcome (too coarse across reruns); drop blocked bytes (loses useful diagnosis); treat blocked as warning (violates gate).

## Decision 3: Notices coexist without changing precedence

**Decision**: Preserve independent advisory/degradation facts, but render blocked delivery as primary.

**Rationale**: This permits spec 047 cleanup/narration notices without weakening F2 remediation.

**Alternatives considered**: One mutable notice slot (causes overwrites); concatenate strings in pipeline (loses machine-readable semantics).

## Decision 4: No new blocked artifact family

**Decision**: Offer retained blocked bytes only in the current session and do not emit accepted artifact events.

**Rationale**: Matches existing persistence tests and avoids retention expansion.

**Alternatives considered**: Persist under `.run/ui_results/` (mislabels output); new long-term diagnostic family (unjustified scope).
