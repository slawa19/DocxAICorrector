# Research: Run-Scoped Formatting Diagnostics

## Decision 1: Dual run and source ownership

**Decision**: Every live artifact records non-empty run id and source token; automatic collection requires both.

**Rationale**: Run alone protects reruns; source additionally guards misrouted context. Filename and time are not identities.

**Alternatives considered**: Source only (same-source reruns collide); run only (weaker cross-check); per-thread global (unsafe concurrency).

## Decision 2: Metadata-backed exact collection

**Decision**: Discover candidates under the existing root but accept only readable artifacts whose ownership envelope exactly matches.

**Rationale**: Minimal storage change and compatible family-wide retention; removes mtime semantics.

**Alternatives considered**: Per-run directory tree (retention/empty-dir complexity); mtime plus token prefix (still heuristic); serialize runs (breaks supported concurrency).

## Decision 3: Collision-safe filename plus envelope

**Decision**: Include sanitized ownership/stage and a uniqueness component in filenames, while treating JSON envelope as authoritative.

**Rationale**: Prevents overwrite; metadata supports validation and replay.

**Alternatives considered**: Timestamp only (collides); filename only (metadata tampering/ambiguity); overwrite same stage (loses evidence).

## Decision 4: Legacy is replay-only

**Decision**: Unscoped artifacts remain explicitly readable but never auto-collected into a live run.

**Rationale**: Honest unknown ownership without destroying historical evidence.

**Alternatives considered**: Infer by mtime/name (reintroduces bug); delete/migrate all legacy files (unnecessary/destructive).

## Decision 5: Keep policy unchanged

**Decision**: Owned paths replace contaminated paths at existing consumers. Thresholds and review/gate classification do not change.

**Rationale**: F12 is provenance isolation, not quality-policy redesign.

**Alternatives considered**: Suppress all diagnostics (vacuum); convert review coverage to gate (forbidden).

## Decision 6: Classify every remaining writer/collector

**Decision**: `pipeline/support.py` marker diagnostics are live-run artifacts and require the current run/source pair. `validation/structural.py` target-alignment diagnostics are explicit offline validation/replay artifacts and are never auto-owned by a live run. `_pipeline.py`'s recent-file compatibility helper is offline-only and must be replaced by explicit paths/ownership or removed; it cannot retain mtime collection semantics.

**Rationale**: Leaving any writer or facade unclassified would either break after ownership becomes required or preserve a hidden contamination path.

**Alternatives considered**: Optional ownership for every caller (allows live unscoped writes); retain `_collect_recent_*` for tests (reintroduces forbidden fallback); force offline validators into a live UI run identity (misstates provenance).

## Implementation reconfirmation (2026-07-20)

- Normal live formatting writes originate in `generation/formatting_transfer.py` and are reached through both the initial DOCX build and the deferred reader-cleanup rebuild.
- Marker/block failure diagnostics originate in `pipeline/support.py` and receive ownership from the active `ProcessingContext` through `pipeline/block_failures.py`.
- Both automatic collection points are in `pipeline/late_phases.py`; each now uses the same exact `run_id` + `source_token` pair as its writer.
- `validation/structural.py` consumes live production diagnostics only from the exact run event and retains the exact path returned by its offline trace writer; shared-directory snapshot discovery is removed.
- The former `_pipeline.py` recent-file facade and real-validation `recent_scan` fallback have no remaining executable call sites. Historical report files are evidence only and are not runtime collectors.

## Independent-review remediation (2026-07-20)

- Deferred reader-cleanup builds treat any changed exact-owned diagnostics set as authoritative report, acceptance, UI, activity, and event evidence; only the existing caption-conflict rule can turn diagnostics into a delivery gate.
- Reserved envelope fields (`stage`, `generated_at_epoch_ms`, `ownership`) are written after diagnostic details and cannot be overridden by caller payloads.
- Live test fixtures use the same ownership envelope as production; no fixture-only fallback was introduced.
- Structural and real-document validation no longer scan a shared directory before/after a run. Live paths come from the run event, while an offline trace is retained only through the exact path returned by its writer.
