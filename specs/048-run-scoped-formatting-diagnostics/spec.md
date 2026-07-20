# Feature Specification: Run-Scoped Formatting Diagnostics

**Feature Branch**: `[048-run-scoped-formatting-diagnostics]`

**Created**: 2026-07-20

**Status**: Draft

**Input**: User description: "Tie formatting-diagnostics artifacts and their collection to exactly one processing run and source so concurrent runs cannot affect each other's quality verdict or UI review data, while preserving existing retention and logging contracts."

**Date**: 2026-07-20

**Owner surface**: formatting-diagnostics persistence, pipeline collection, quality reporting, and UI feedback

**Companion**: `docs/reviews/CODE_REVIEW_ROUND10_2026-07-20.md` (F12); `docs/LOGGING_AND_ARTIFACT_RETENTION.md`; final-evidence consumer `specs/047-reader-cleanup-production-parity/spec.md`

**Changelog**:

- 2026-07-20 — Initial specification from the agreed round-10 F12 finding, verified against current `main @ 23020a9`.
- 2026-07-20 — Cross-spec review narrowed verdict wording: this feature scopes diagnostics-derived evidence only and does not make review data a gate or replace other acceptance evidence.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Keep each run's verdict independent (Priority: P1)

As a user processing a document while another document is being processed, I need every diagnostics-derived contribution to my quality verdict and delivery decision to use only diagnostics produced for my run and source, so another user's or session's document cannot cause a false warning, false block, or false clean result.

**Why this priority**: The application permits two processing workers by default. A diagnostic from a nearby run can currently enter the same time-based collection window and directly influence quality evaluation.

**Independent Test**: Execute two overlapping synthetic processing runs with different run and source identities, make only one produce a delivery-relevant formatting conflict, and verify that each run's report, verdict, and terminal outcome use only its own artifacts.

**Acceptance Scenarios**:

1. **Given** overlapping Run A and Run B for different sources, with a conflict diagnostic produced only by Run A, **When** both runs evaluate quality, **Then** Run A sees the conflict and Run B does not.
2. **Given** overlapping runs that write diagnostics during the same wall-clock interval, **When** each run collects its artifacts, **Then** collection is determined by run/source ownership rather than creation or modification time.
3. **Given** Run A has a diagnostic that is delivery-blocking under existing policy and Run B has only informational diagnostics, **When** both complete, **Then** each receives its own correct terminal outcome without cross-run contamination and no new blocking rule is introduced.

---

### User Story 2 - Show only this result's review data (Priority: P2)

As a user reviewing a completed document, I need the UI notice, activity text, saved quality report, and formatting review data to describe that exact result, so I can trust the warnings and artifact links shown alongside it.

**Why this priority**: The same collected artifact list feeds user-facing feedback, quality-report fields, and log paths. Incorrect ownership therefore propagates beyond an internal diagnostic list.

**Independent Test**: Complete two overlapping runs with distinguishable diagnostic counts and verify that each result notice, saved review data, quality report, and diagnostics event contains only the paths and counts owned by that run.

**Acceptance Scenarios**:

1. **Given** two runs with different formatting-review counts, **When** their result bundles are presented, **Then** each UI notice reports only its own count and severity.
2. **Given** a run that produces no formatting diagnostics while another run produces several, **When** the first run completes, **Then** it does not claim that formatting diagnostics were detected.
3. **Given** a diagnostics-detected log event for a run, **When** an operator follows its artifact paths, **Then** every path belongs to the logged run and source.

---

### User Story 3 - Preserve diagnostics operations and retention (Priority: P3)

As an operator, I need run ownership to be added without losing diagnostics on write failure, without unbounded disk growth, and without breaking replay of retained artifacts, so isolation does not weaken observability.

**Why this priority**: Formatting diagnostics are operational evidence. Scope isolation is incomplete if it silently drops same-run artifacts or bypasses the established seven-day/100-artifact retention policy.

**Independent Test**: Write artifacts for multiple run/source scopes, exercise collection, pruning, write failure, and retained-artifact loading, then verify exact ownership, existing warning events, age/count limits, and replayability.

**Acceptance Scenarios**:

1. **Given** more retained diagnostics than the configured family-wide count limit or diagnostics older than the configured age limit, **When** pruning runs, **Then** the existing age and total-count bounds still apply across the whole formatting-diagnostics family.
2. **Given** a diagnostics write failure, **When** processing continues fail-open, **Then** the existing warning event remains emitted with actionable error context.
3. **Given** an older retained artifact without run ownership metadata, **When** a new processing run collects diagnostics, **Then** the legacy artifact is not silently claimed by that run, while explicit offline replay remains possible.

### Edge Cases

- Two runs may process different files with the same display filename; filename equality is not run ownership.
- Two reruns may process identical source bytes and therefore share source identity; distinct run identity still keeps their diagnostics separate.
- Two writers may emit the same stage at the same millisecond; neither run's artifact may overwrite the other's, and multiple artifacts within one run must also remain distinct.
- A run may write more than one diagnostics artifact across build, reader-cleanup rebuild, structural validation, or marker-related stages; all and only its own artifacts remain collectable after each phase.
- A run may produce no artifacts. The empty result is valid and must not fall back to a global recent-file scan.
- A malformed, deleted, or unreadable owned artifact remains fail-open for diagnostics loading, without allowing an unrelated artifact to substitute for it.
- A non-UI validation/replay workflow may read explicitly selected historical paths; historical replay is not equivalent to automatic ownership by a live processing run.

## Verified findings

- **Collection is global and time-based** — the production collector scans every top-level JSON file in the shared diagnostics directory and includes each file whose modification time is at least the run-start threshold minus one second; it accepts no run or source identity, `src/docxaicorrector/generation/formatting_diagnostics_retention.py:19` and `src/docxaicorrector/generation/formatting_diagnostics_retention.py:25` (verified 2026-07-20 on `main @ 23020a9`).
- **Artifacts carry no ownership envelope** — the writer accepts stage, diagnostics, optional filename prefix/directory, and timestamp, then writes stage and generation time plus the diagnostic payload; neither the writer contract nor the generated filename requires run/source identity, `src/docxaicorrector/generation/formatting_diagnostics_retention.py:35` and `src/docxaicorrector/generation/formatting_diagnostics_retention.py:44` (verified 2026-07-20 on `main @ 23020a9`).
- **Normal formatting restore cannot provide run ownership** — its diagnostics writer wrapper forwards only stage, diagnostics, and the shared directory, `src/docxaicorrector/generation/formatting_transfer.py:153` (verified 2026-07-20 on `main @ 23020a9`).
- **The pipeline performs the unsafe collection twice** — initial DOCX build collection uses only `build_started_at_epoch` and the shared directory, while a deferred reader-cleanup build recollects through the same time-window contract, `src/docxaicorrector/pipeline/late_phases.py:507` and `src/docxaicorrector/pipeline/late_phases.py:787` (verified 2026-07-20 on `main @ 23020a9`).
- **Foreign paths can affect visible and delivery behavior** — the collected list drives user feedback and the `formatting_diagnostics_artifacts_detected` event, `src/docxaicorrector/pipeline/late_phases.py:513` and `src/docxaicorrector/pipeline/late_phases.py:530`; it is also loaded into quality evaluation and persisted report fields, `src/docxaicorrector/pipeline/quality_gate.py:1196`, `src/docxaicorrector/pipeline/quality_gate.py:1211`, and `src/docxaicorrector/pipeline/quality_gate.py:1844` (verified 2026-07-20 on `main @ 23020a9`).
- **Required identities already exist at the pipeline boundary** — processing context carries both `source_token` and `run_id`, `src/docxaicorrector/pipeline/contracts.py:218`; the background runtime generates a fresh UUID-derived run id for each start, `src/docxaicorrector/processing/processing_runtime.py:1954` (verified 2026-07-20 on `main @ 23020a9`).
- **Concurrent overlap is a current supported state** — the process-wide admission limit defaults to two workers, `src/docxaicorrector/processing/processing_runtime.py:127`; the focused canonical WSL test `bash scripts/test.sh tests/test_processing_runtime.py::test_processing_admission_gate_caps_concurrency -vv -x` passed on 2026-07-20 against the current workspace at `main @ 23020a9`, confirming that two admitted runs are not a hypothetical future mode.
- **Retention is already bounded** — the family has a seven-day age limit and 100-artifact cap enforced on write, `src/docxaicorrector/generation/formatting_diagnostics_retention.py:10` and `src/docxaicorrector/generation/formatting_diagnostics_retention.py:56`; the canonical documentation records the same contract for `.run/formatting_diagnostics/*.json`, `docs/LOGGING_AND_ARTIFACT_RETENTION.md:180` and `docs/LOGGING_AND_ARTIFACT_RETENTION.md:186` (verified 2026-07-20).
- **Write failure is intentionally fail-open but observable** — a failed diagnostics write emits `formatting_diagnostics_write_failed` and does not fail the processing run, `src/docxaicorrector/generation/formatting_diagnostics_retention.py:58` (verified 2026-07-20 on `main @ 23020a9`).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Every formatting-diagnostics artifact produced within a live processing workflow MUST be associated with exactly one non-empty processing run identity and one source identity.
- **FR-002**: Automatic diagnostics collection for a live run MUST return only artifacts whose run and source identities both match that run; modification time, filename, stage, or directory recency MUST NOT establish ownership.
- **FR-003**: A distinct rerun of identical source bytes MUST have an independent diagnostics set even when the source identity is unchanged.
- **FR-004**: Overlapping runs for different sources, the same source, or the same display filename MUST NOT read, aggregate, report, gate on, log as detected, or expose each other's diagnostics.
- **FR-005**: All diagnostics-producing stages invoked within a processing run MUST receive the same run/source scope, including initial formatting restore and any deferred or post-cleanup DOCX rebuild.
- **FR-006**: Recollection after a deferred build MUST stay within the original run/source scope and include newly produced owned artifacts without reintroducing a global time-window fallback.
- **FR-007**: Multiple artifacts from one run and repeated writes from the same stage MUST remain distinct and collectable; concurrent writes MUST NOT overwrite another artifact.
- **FR-008**: A run with no owned artifacts MUST produce an empty diagnostics set. It MUST NOT claim unscoped, legacy, or recent foreign artifacts as a fallback.
- **FR-009**: Every diagnostics-derived input to the quality verdict, formatting review counts/items, delivery decision, UI result notice, activity feedback, and saved quality report MUST come only from the run's owned diagnostics set. Other established acceptance evidence remains in force and is not replaced by this set.
- **FR-010**: The existing `formatting_diagnostics_artifacts_detected` event MUST retain its event identity and exact-path reporting behavior, and its reported paths MUST be limited to the current run/source scope.
- **FR-011**: The existing `formatting_diagnostics_write_failed` fail-open warning contract MUST remain intact; ownership failures MUST be observable and MUST NOT be hidden by collecting unrelated artifacts.
- **FR-012**: The existing formatting-diagnostics retention policy MUST remain seven days and at most 100 artifacts across the entire artifact family, not 100 per run/source. Ownership grouping MUST NOT permit unbounded empty directories or metadata.
- **FR-013**: Existing retained artifacts MUST remain explicitly loadable for offline validation/replay. Artifacts lacking ownership metadata MUST NOT be automatically associated with a new live run.
- **FR-014**: The diagnostics family MUST remain rooted under `.run/formatting_diagnostics/`, and every path surfaced to logs, reports, UI-linked review data, or validation tooling MUST resolve to an actual retained artifact.
- **FR-015**: The change MUST preserve the default processing concurrency of two and MUST NOT serialize processing as a substitute for correct ownership.
- **FR-016**: The change MUST preserve existing quality policy: run scoping changes which evidence belongs to a run, but MUST NOT create a new gate, alter thresholds, or turn formatting coverage review data into a verdict gate.
- **FR-017**: Run/source association MUST be propagated without process-global mutable ownership state that could be overwritten by another concurrent run.

### Key Entities

- **Processing run identity**: A unique identity for one invocation, distinct across retries/reruns even for identical source bytes.
- **Source identity**: The stable identity of the uploaded source associated with a processing run.
- **Formatting-diagnostics artifact**: A retained diagnostic payload with stage, generation metadata, exact path, and explicit run/source ownership when created by a live run.
- **Owned diagnostics set**: The complete set of readable artifacts whose run and source identities match one processing context.
- **Legacy/unscoped artifact**: A retained artifact created before or outside the live run-ownership contract; eligible for explicit replay but never automatic live-run collection.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: In an acceptance test with two overlapping runs and at least one artifact per run, 100% of artifacts returned to each run belong to that run and source, with zero foreign paths.
- **SC-002**: In an overlapping-run test where only Run A has a conflict that produces a warning or block under existing policy, Run A alone receives that existing-policy outcome and Run B completes with no conflict-derived warning or block.
- **SC-003**: In same-source rerun and same-filename/different-source tests, each run receives exactly its own expected artifact count and review-item count.
- **SC-004**: A zero-artifact run returns exactly zero diagnostics even while another admitted run writes artifacts inside the same wall-clock second.
- **SC-005**: Repeated same-stage writes at identical supplied timestamps produce the expected number of distinct retained artifacts with no overwrite.
- **SC-006**: Retention acceptance tests demonstrate that the entire formatting-diagnostics family never retains more than 100 artifacts after pruning and removes artifacts older than seven days, regardless of the number of run scopes.
- **SC-007**: Existing write-failure and diagnostics-detected event contracts remain observable, and 100% of paths in a run's detected event match its owned diagnostics set.
- **SC-008**: Existing explicitly selected historical diagnostics remain replayable, while 100% of unscoped legacy artifacts are excluded from automatic live-run collection.

## Non-goals

- Reducing processing concurrency to one, adding a global formatting lock, or otherwise avoiding overlap — concurrency of two is supported behavior and must remain.
- Changing quality thresholds, warning wording, caption-conflict policy, delivery-gate semantics, or the review-data status of formatting coverage — this feature fixes evidence ownership only.
- Creating a new diagnostics artifact family or moving artifacts outside `.run/formatting_diagnostics/` — the existing family and operational discovery root remain canonical.
- Increasing retention limits per run or retaining every run indefinitely — the current seven-day/100-artifact family-wide bounds remain sufficient.
- Associating legacy artifacts with a current run by timestamp, source filename, content similarity, or inference — unknown ownership remains unknown.
- Redesigning all project artifacts around one global run-directory architecture — only formatting diagnostics and their direct consumers are in scope.
- Changing source-token generation, processing admission policy, session state, or result-bundle identity beyond what is necessary to carry existing run/source ownership.

## Anti-regression

- **Concurrent contamination proof**: add a deterministic two-run test in which a conflict artifact from Run A is written during Run B's time window; Run B MUST collect zero foreign paths and MUST not inherit Run A's warning or block.
- **Same-run anti-vacuum proof**: the same test MUST prove Run A still collects and acts on its own conflict artifact. A filter that returns nothing for every run is not a valid fix.
- **Clean-run proof**: a run with no owned diagnostics remains clean while a concurrent run writes one or more artifacts.
- **Same-source rerun proof**: two run identities sharing one source token remain isolated, proving that source identity alone is insufficient.
- **Different-source proof**: two sources with the same display filename remain isolated, proving that filename is not ownership.
- **Deferred-build proof**: initial and post-reader-cleanup collection use the same run/source ownership and the final pass includes newly written same-run diagnostics only.
- **Collision proof**: repeated same-stage writes at the same timestamp remain distinct; neither same-run nor cross-run data is overwritten.
- **Retention anti-vacuum proof**: artifacts spread across multiple run scopes are counted together for the existing max-100 family cap, and age pruning still removes expired files. Per-run grouping MUST NOT multiply the cap.
- **Logging proof**: `formatting_diagnostics_artifacts_detected` retains exact paths but contains no foreign path; `formatting_diagnostics_write_failed` remains emitted on write failure.
- **Legacy replay proof**: an unscoped historical artifact remains loadable through an explicit replay path but is excluded from live automatic collection.
- Existing focused quality-report and UI-feedback tests MUST remain green with owned paths; their severity and wording change only when eliminating previously foreign evidence changes the truthful outcome.
- No credit/subtraction rule is introduced. Formatting coverage remains review data, and cross-run isolation MUST NOT be implemented by suppressing genuine same-run review items.

## Assumptions

- Production background processing continues to supply a non-empty unique run identity and a stable source token before diagnostics-producing stages begin.
- One processing run may legitimately produce several formatting diagnostics across stages; ownership is one-to-many, not one artifact per run.
- Offline validators and replay tools can continue to load explicitly named artifact paths without treating those paths as automatically owned by a live UI run.
- Existing event names, artifact root, seven-day TTL, 100-artifact cap, and fail-open write behavior are externally useful operational contracts and remain stable.
- Focused and full verification in later phases will use canonical WSL entry points from `AGENTS.md`; specification creation does not require a full-suite run.
