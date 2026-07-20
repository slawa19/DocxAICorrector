# Data Model: Run-Scoped Formatting Diagnostics

## DiagnosticsOwnership

- `run_id`: non-empty unique processing invocation id
- `source_token`: stable source identity

Validation: both required for live-write/auto-collection; exact equality required.

## FormattingDiagnosticsArtifact

- ownership envelope
- stage
- generated timestamp
- diagnostics payload
- collision-safe exact path

Relationship: one run/source scope owns zero-to-many artifacts; repeated stages remain separate.

## OwnedDiagnosticsSet

- requested ownership
- readable matching artifact paths
- loaded diagnostics/review data

Invariant: contains zero foreign or unscoped paths. Empty is valid and never falls back to recent files.

## LegacyArtifact

- historical payload without complete ownership
- available only through explicit path replay

## Retention transitions

`write owned artifact → prune whole family by age → prune whole family to max 100`

Ownership grouping never creates separate caps.
