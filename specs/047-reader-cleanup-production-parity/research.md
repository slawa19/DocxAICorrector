# Research: Reader Cleanup Production Parity

## Decision 1: Explicit config mapping, default unchanged

**Decision**: Map resolved `reader_cleanup_default` to the effective pipeline setting for UI runs; retain false default and translation/off guards.

**Rationale**: Fixes key mismatch without adding UI or widening rollout.

**Alternatives considered**: Rename all config keys (broad migration); enable by default (risk); add toggle (out of scope).

## Decision 2: Spec 048 ownership precedes final evidence

**Decision**: Implement 048 first. Changed/no-op cleanup finalization consumes final run/source-owned diagnostics; no mtime bridge.

**Rationale**: Prevents deliberately introducing a known contamination path only to remove it next.

**Alternatives considered**: Temporary build-window list (contradicts reviewed contract); serialize runs (breaks concurrency).

## Decision 3: Cooperative cancellation at side-effect boundaries

**Decision**: Check the existing stop predicate before cleanup, between provider calls, before rebuild/re-gate, before/between narration calls and before persistence/completion.

**Rationale**: Honest and provider-neutral; in-flight calls may return.

**Alternatives considered**: Kill threads/network calls (unsafe/provider-specific); check only at phase entry (too coarse).

## Decision 4: Typed degradation facts, one delivery authority

**Decision**: Preserve cleanup and narration advisory facts independently through spec-044 result bundle notices. Delivery disposition remains authoritative.

**Rationale**: Avoids `last_error` overwrite and false reclassification.

**Alternatives considered**: One mutable error string (current defect); turn cleanup advisory into failure (breaks fail-open policy).

## Decision 5: Narration follows final cleanup lineage

**Decision**: For translation cleanup only, project narration-eligible final content using existing lineage/structural exclusions. If mapping is ambiguous, omit narration with warning.

**Rationale**: Avoids contradictory output and Constitution VII guessing.

**Alternatives considered**: Use pre-cleanup chunks (stale); narrate all final Markdown (leaks excluded regions); text heuristics (forbidden).

## Decision 6: Standalone audiobook is unchanged

**Decision**: Do not route standalone audiobook through cleanup projection, new omission rules, or new warnings.

**Rationale**: Reader cleanup is translation-only and audiobook has its own authoritative narration path.
