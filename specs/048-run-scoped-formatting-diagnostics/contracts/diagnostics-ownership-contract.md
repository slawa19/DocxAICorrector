# Contract: Formatting Diagnostics Ownership

## Live write

- Requires non-empty `run_id` and `source_token` from processing context.
- Writes both into the artifact envelope.
- Produces a unique path for repeated stage/time writes.
- On write failure emits existing `formatting_diagnostics_write_failed` and remains fail-open.
- Normal formatting restore and marker/block diagnostic writes in `pipeline/support.py` use this live contract.

## Automatic collection

- Requires the current run/source ownership pair.
- Returns only readable exact matches.
- Never uses mtime, display filename, stage or recency as ownership.
- Empty match returns empty; no global fallback.

## Consumers

- Initial and deferred/final builds use the same ownership pair.
- Diagnostics-derived quality, review, UI, report and log inputs use only owned paths.
- `formatting_diagnostics_artifacts_detected` keeps exact owned paths.
- Other acceptance evidence and policy remain unchanged.

## Retention/replay

- Root remains `.run/formatting_diagnostics/`.
- Seven-day and max-100 limits apply across all owners.
- Unscoped legacy artifacts are explicit-replay only.
- `validation/structural.py` target-alignment traces are explicit offline validation artifacts. Their producing validation run may retain explicit paths/snapshots, but live automatic collection never claims them.
- The `_pipeline.py` compatibility facade and real-document validation helpers must accept explicit paths or an explicit owned scope; no public/private helper may preserve recent-mtime discovery as live ownership.

## Dependency

Spec 047 starts after this contract is implemented; it receives final owned diagnostics and adds no mtime compatibility path.
