# Research: Stable Source and Preparation Identity

## Decision 1: Separate source identity from payload integrity

**Decision**: Preserve the original upload token as authoritative and store size plus full stable digest for exact normalized bytes.

**Rationale**: Converter output may vary without changing the uploaded source; one hash cannot truthfully represent both facts.

**Alternatives considered**: Recompute token from DOCX (causes drift); persist original bytes too (duplicates large sources); trust stored token without digest (cannot detect corruption).

## Decision 2: Restore a token-bearing normalized payload

**Decision**: After validation, reconstruct the existing frozen upload payload with normalized bytes, original token, source format and conversion provenance.

**Rationale**: Downstream already honors a frozen payload token and skips materialization when bytes are normalized.

**Alternatives considered**: Rebuild an anonymous in-memory upload (loses identity); reconvert original PDF/DOC (unavailable and wasteful).

## Decision 3: Reject unverifiable legacy records

**Decision**: Missing identity/integrity metadata makes the ephemeral record unavailable; require fresh upload.

**Rationale**: Safe and bounded; guessing recreates F3.

**Alternatives considered**: Derive from normalized bytes (wrong identity); implicit metadata migration (original identity cannot be proven).

## Decision 4: Mirror language normalization in the outer marker

**Decision**: Add canonical source and target language segments to the UI request marker using the same default/trim/case semantics as the prepared-source key.

**Rationale**: Prevents stale UI context without invalidating semantically equivalent requests.

**Alternatives considered**: Clear all preparation on any widget rerun (over-invalidates); change only inner cache key (already correct).
