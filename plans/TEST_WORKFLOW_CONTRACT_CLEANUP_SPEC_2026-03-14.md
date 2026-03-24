# Test Workflow Contract Cleanup Spec

Date: 2026-03-14

## 1. Problem Statement

The repository currently mixes two incompatible stories about how tests are supposed to run:

- the implemented VS Code path already runs tests directly in WSL through `bash scripts/test.sh ...`;
- multiple docs still describe PowerShell test wrappers as an official entry path;
- parts of the Windows-side PowerShell layer still exist only to support the legacy test path.

This creates contract drift. A user or agent can read one document, follow an outdated path, and get behavior that is no longer the intended architecture.

## 2. Decision

The repository will keep exactly one supported test execution contract:

1. Primary CLI entry point: `bash scripts/test.sh ...` from WSL.
2. Primary editor entry point: VS Code test tasks that invoke WSL/bash directly.
3. Windows PowerShell remains supported only for application lifecycle and diagnostics.

Legacy PowerShell test wrappers are not part of the supported contract and are scheduled for removal.

## 3. Goals

1. Remove competing documentation and instructions for test execution.
2. Make the supported test path obvious to humans and AI agents.
3. Shrink Windows-side test-specific code until only lifecycle-related PowerShell remains.
4. Remove test coverage that exists only for the deprecated PowerShell test path.

## 4. Non-Goals

1. Replacing lifecycle scripts with a new Windows orchestration model.
2. Refactoring application startup, shutdown, or status flows beyond what is needed to isolate test-related logic.
3. Changing the WSL dispatcher behavior for application runtime unless dead test-path code is entangled with it.

## 5. Constraints And Rationale

1. Documentation cleanup must happen before wrapper deletion.
Reason: the repository currently documents `run-tests.ps1`, `run-test-file.ps1`, and `run-test-node.ps1` as supported entry points. Deleting them first would silently break documented behavior.

2. Shared PowerShell cleanup must be selective.
Reason: `_shared.ps1` contains both test-only helpers and lifecycle-critical helpers. `Normalize-TestTarget`, `Split-TestTarget`, `Test-IsWindowsAbsolutePath`, and `Test-IsUnderProjectRoot` are tied to the deprecated test wrappers. `Invoke-WslInProject`, `Test-IsTransientWslFailure`, and `Reset-WslTransport` still serve lifecycle code and cannot be removed just because test wrappers are deprecated.

3. Historical planning documents may retain superseded detail only if they are clearly marked as historical.
Reason: archival context is useful, but source-of-truth docs must not point readers to stale operational paths.

## 6. Current State Summary

1. Canonical implementation already exists:
- `scripts/test.sh`
- `.vscode/tasks.json`
- `.vscode/settings.json`

2. Contradictory official guidance still exists in multiple docs and rules files.

3. Legacy PowerShell test wrappers still exist and still require test-target normalization helpers from `_shared.ps1`.

4. Test coverage still partially assumes the PowerShell test path matters as a contract.

## 7. Target State

1. Humans and agents are instructed to run tests only through `scripts/test.sh` or the WSL VS Code tasks.
2. PowerShell is documented as application lifecycle-only, plus optional log-tail support.
3. Legacy PowerShell test wrappers are either:
- deleted, or
- retained temporarily with an explicit deprecation warning and no claim of official support.
4. `_shared.ps1` no longer contains test-only helpers after wrapper removal.
5. Test coverage validates only the supported contract, plus at most a minimal compatibility/deprecation check during the transition.

## 8. Execution Plan

### Phase 1. Freeze The Supported Contract

Actions:

1. Update `README.md`, `CONTRIBUTING.md`, `docs/WORKFLOW_AND_IMAGE_MODES.md`, and `docs/AI_AGENT_DEVELOPMENT_RULES.md` to describe only the WSL/bash test path as official.
2. Keep PowerShell lifecycle scripts documented as supported.
3. Mark PowerShell test wrappers as deprecated compatibility shims.

Done when:

1. No source-of-truth doc presents PowerShell test wrappers as the recommended path.
2. Every core workflow doc points to `bash scripts/test.sh ...` and the WSL tasks.

### Phase 2. Reduce Transition Surface

Actions:

1. Add explicit deprecation warnings to `run-tests.ps1`, `run-test-file.ps1`, and `run-test-node.ps1`.
2. Reduce tests that validate PowerShell test-path behavior to the smallest useful compatibility coverage.
3. Add or keep tests that validate:
- `scripts/test.sh` as the canonical entry point;
- VS Code tasks invoke WSL/bash directly;
- docs do not advertise the old test-wrapper contract.

Done when:

1. Users see an explicit warning if they invoke the deprecated wrappers.
2. Regression coverage no longer treats the deprecated path as first-class.

### Phase 3. Remove Test-Only PowerShell Infrastructure

Prerequisite:

1. No supported doc or workflow depends on the legacy test wrappers.
2. Compatibility need for those wrappers is confirmed to be zero or intentionally ended.

Actions:

1. Delete `run-tests.ps1`, `run-test-file.ps1`, and `run-test-node.ps1`.
2. Remove test-only helpers from `_shared.ps1`.
Likely candidates:
- `Split-TestTarget`
- `Normalize-TestTarget`
- `Test-IsWindowsAbsolutePath`
- `Test-IsUnderProjectRoot`
3. Remove obsolete wrapper-specific test logging that exists only for the deleted full-pytest PowerShell wrapper.
4. Simplify tests that previously validated Windows-side test selector normalization.

Done when:

1. No Windows-side script remains solely for test execution.
2. `_shared.ps1` is lifecycle-focused.

### Phase 4. Final Consistency Pass

Actions:

1. Remove stale references from remaining docs, comments, tasks, and historical notes where needed.
2. Mark earlier planning material as superseded where it still describes wrapper-driven testing.
3. Run targeted lifecycle smoke checks and relevant pytest suites.

Done when:

1. The repository exposes one unambiguous test workflow.
2. Lifecycle scripts continue to work.

## 9. Success Criteria

1. There are no competing supported test workflows in user-facing docs.
2. `scripts/test.sh` and WSL test tasks are the only documented official test entry points.
3. PowerShell remains only where it is operationally justified.
4. The repository no longer depends on the PowerShell-to-WSL bridge for normal test execution.

## 10. Initial Implementation Scope

Status update: completed in the 2026-03-14 cleanup series.

1. Source-of-truth docs now point only to `scripts/test.sh` and direct WSL VS Code test tasks.
2. Legacy PowerShell test wrappers and their test-only helper layer were removed.
3. The WSL dispatcher no longer exposes wrapper-driven test actions.

This spec remains as the rationale and execution record for the cleanup.

Initial implementation scope was:

1. document the single supported test contract;
2. remove legacy wrapper-driven test entry points;
3. add regression coverage that locks in the new contract.