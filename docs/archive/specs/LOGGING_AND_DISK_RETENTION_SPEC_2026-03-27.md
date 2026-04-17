# Logging and Disk Retention Spec

Date: 2026-03-27
Status: Proposed
Scope: runtime log-volume reduction, disk-write minimization, retention hardening, and `.run` hygiene within the existing monolith
Primary inputs: `docs/archive/specs/ARCHITECTURE_REFACTORING_SPEC_2026-03-25.md`, `docs/archive/specs/AI_STRUCTURE_RECOGNITION_SPEC_2026-03-26.md`, `README.md`, `AGENTS.md`

## 1. Problem Statement

The current application behavior is functionally acceptable, but the runtime footprint is still noisier and more disk-write-heavy than necessary for a WSL-first local monolith that can stay alive for long sessions.

The main issue is not one catastrophic leak. It is the cumulative effect of several independently reasonable behaviors:

- application logging is configured conservatively for persistence but still defaults to `INFO`, which keeps high-churn operational events in the hot path even when they are mostly useful only for debugging;
- multiple runtime and control-plane logs under `.run/` do not share a consistent rotation or retention policy, so total disk usage depends on uptime rather than on an explicit contract;
- Streamlit liveness signaling currently writes `.run/app.ready` on every frame finalization, while fragments execute with `run_every=1` and `run_every=2`, creating permanent small writes during idle uptime;
- document and image processing paths emit verbose informational events that are disproportionately expensive relative to their debugging value, especially for large documents and retry-heavy image flows;
- formatting diagnostics artifacts are intentionally useful, but their directory currently has no documented cleanup policy, TTL, or count cap;
- the repository already distinguishes some short-lived runtime artifacts from more durable validation artifacts, but that split is not yet formalized enough to guide retention behavior.

This is now worth specifying because the current system is stable enough that operational hygiene can be tightened without architectural redesign. The goal is to reduce unnecessary writes, constrain `.run` growth, and preserve the debugging paths that matter.

## 2. Goals

1. Reduce hot-path disk writes and runtime log volume without removing critical observability.
2. Make application log verbosity configurable through a supported runtime contract, with safe defaults for production-like local runs.
3. Introduce explicit rotation and retention behavior for `.run/project.log` and bounded-growth behavior for `.run/streamlit.log`.
4. Reduce high-cardinality payload logging in document and image processing paths, especially on steady-state success flows.
5. Add a concrete retention and cleanup policy for `.run/formatting_diagnostics` artifacts.
6. Optionally enforce total-size and count guardrails for `.run` so long uptimes cannot grow disk usage unboundedly.
7. Explicitly distinguish production runtime concerns from developer/test artifact concerns so cleanup rules do not break validation workflows.
8. Preserve the current monolith, WSL-first runtime contract, and existing user-visible workflow semantics.

## 3. Non-Goals

This spec does not authorize the following:

- replacing the current logging stack with a new logging framework, structured-log backend, or external collector;
- redesigning the app into services, workers, or a separate supervisor process;
- changing the WSL-first runtime contract or moving `.run` ownership out of the repository;
- deleting or disabling diagnostics that are required for real-document validation without replacing them with a bounded equivalent;
- broad refactors of `document_pipeline.py`, `image_generation.py`, or Streamlit composition for stylistic reasons unrelated to write-volume reduction;
- introducing background daemons or OS-specific retention agents outside the repository scripts;
- changing `tests/artifacts/...` retention semantics as if they were production runtime state.

## 4. Protected Contracts

The following contracts remain protected throughout this work.

1. WSL-first runtime remains canonical. Runtime behavior is still defined by the project under WSL at `/mnt/d/www/projects/2025/DocxAICorrector`.
2. The application remains a monolith. Logging and cleanup improvements must fit the current composition shape.
3. Startup-sensitive behavior must remain protected. No change may add heavy synchronous directory scans or cleanup work to the early interactive render path.
4. Existing runtime logs under `.run/` remain local debugging artifacts rather than product-facing audit logs.
5. `restart_store.py` TTL cleanup for `.run/restart_*` and `.run/completed_*` remains in force at 12 hours unless a later task explicitly supersedes it.
6. Real-document validation and dev artifacts under `tests/artifacts/...` remain separate from production runtime retention rules.

Any implementation that adds retention or cleanup must preserve the ability to diagnose the current run, recent failures, and formatting-regression cases without needing external tooling.

## 5. Current-State Summary

The following implementation facts are treated as verified baseline context for this spec.

### 5.1 Logger baseline

- `logger.py` writes application events to `.run/app.log` through `_WSLSafeRotatingFileHandler`.
- The handler is configured with `maxBytes=1_000_000` and `backupCount=3`.
- The current rotation therefore also creates bounded backup files such as `.run/app.log.1`, `.run/app.log.2`, and `.run/app.log.3`.
- The logger level is currently hard-coded to `logging.INFO` in `logger.py:45`.
- The current design is already rotation-aware for `app.log`, but the verbosity policy is not configurable.
- `logger.py:log_event()` already accepts an arbitrary logging level and delegates to `Logger.log(...)`, so moving specific events from `INFO` to `DEBUG` does not require a logging API redesign.

### 5.2 Project control log baseline

- `scripts/_shared.ps1` appends lines to `.run/project.log` through `Append-ProjectLogEntry()`.
- That path is append-only today and has no built-in rotation, retention, count cap, or size cap.
- This means control-plane activity can accumulate indefinitely across repeated start/stop cycles.

### 5.3 Streamlit process log baseline

- `scripts/project-control-wsl.sh` writes `.run/streamlit.log`.
- The current startup flow truncates that file on process start, which bounds growth across restarts.
- During a single long-running uptime, there is no rotation or periodic truncation, so runtime growth is unbounded until restart.

### 5.4 App-ready marker baseline

- `app.py:_mark_app_ready()` writes `.run/app.ready` on every `_finalize_app_frame()` call.
- `_finalize_app_frame()` is reached from fragments configured with `run_every=1` and `run_every=2`.
- This creates a permanent steady stream of small writes even when the app is idle and healthy.
- `_finalize_app_frame()` also calls `_schedule_stale_persisted_sources_cleanup()`, but that helper already short-circuits after the first successful per-session scheduling via `st.session_state.persisted_source_cleanup_done`; it should still be acknowledged when reviewing hot-path work, but it is not the primary steady-state write source.

### 5.5 High-volume pipeline logging baseline

- `document_pipeline.py` logs `processing_started`, `block_map`, and `block_started` at `INFO`.
- The current `block_map` event logs the full block list with a preview for each block; each preview is already truncated to 120 characters, so the main problem is high cardinality and document-scaled payload shape rather than unlimited per-block text size.
- `image_generation.py` contains many `INFO` events across candidate generation, retry, adaptation, and image-selection paths.
- These logs are most valuable for diagnosis of a failing run, but they are currently emitted in normal success paths as well.

### 5.6 Formatting diagnostics artifact baseline

- `document_pipeline.py` and `formatting_transfer.py` write JSON artifacts to `.run/formatting_diagnostics`.
- `formatting_transfer.py:_write_formatting_diagnostics_artifact()` creates timestamped JSON files.
- No cleanup, TTL policy, or count cap was found for `.run/formatting_diagnostics`.
- `document_pipeline.py:_collect_recent_formatting_diagnostics()` also scans this directory for recent artifacts, so retention changes affect not only validation tooling but also an in-repo runtime consumer.
- Validation tooling under `tests/artifacts/real_document_pipeline/run_lietaer_validation.py` knows how to discover recent formatting diagnostics, so retention changes must preserve per-run discoverability.

### 5.7 Existing retention baseline elsewhere

- `restart_store.py` already provides TTL-based cleanup for `.run/restart_*` and `.run/completed_*`, while the current 12-hour TTL is configured in `app.py` and passed into that helper as `max_age_seconds`.
- Temporary directories created via `TemporaryDirectory()` in `generation.py` and `processing_runtime.py` already follow short-lived workflow semantics and are not the main problem for this spec.

### 5.8 Production runtime vs dev/test artifacts baseline

- Production runtime concerns in scope for this spec live under `.run/`.
- Developer and validation artifacts under `tests/artifacts/...` are not part of the same retention domain and must not be silently cleaned by runtime retention logic.

## 6. Design Principles

Implementation in this wave must follow these principles.

1. Prefer targeted reductions in write volume over broad infrastructure replacement.
2. Keep default runtime observability sufficient for recent failure diagnosis, but move deep trace noise behind `DEBUG` or explicit diagnostics paths.
3. Bound disk growth with simple, local policies: rotation, TTL, count caps, and optional total-size guardrails.
4. Do not add expensive polling or aggressive cleanup to high-frequency UI paths.
5. Separate runtime artifacts from validation artifacts by directory contract, not by guesswork.
6. Preserve current success-path behavior and user-facing outcomes; optimize supporting mechanics, not product logic.
7. Keep retention code deterministic and inspectable so engineers can reason about which files are preserved and why.
8. Reuse existing `.run` ownership patterns where possible instead of inventing a second runtime-artifact subsystem.
9. Prefer one explicit owner per runtime-artifact concern. Event-emitting modules may request diagnostics output, but retention policy, pruning rules, and readiness-marker throttling should not be reimplemented independently in multiple callers.
10. Keep `app.py` orchestration-only for this wave. It may trigger runtime-artifact helpers, but it should not become the long-term owner of retention policy, rollover decisions, or multi-step `.run` hygiene logic.
11. Use one configuration contract for cross-runtime retention settings wherever the same policy must be consumed by Python, Bash, and PowerShell. If a threshold is shared conceptually, the effective setting must not be hard-coded separately in multiple languages without an explicit contract.

### 6.1 Ownership and orchestration rule

- `logger.py` remains the owner of application log configuration and emission plumbing for `.run/app.log`, but not of general `.run` retention for unrelated artifact families.
- `app.py` remains the Streamlit composition root and may orchestrate when a readiness-marker update or cleanup hook is invoked, but helper logic should own the mechanics when that logic grows beyond a trivial call.
- `document_pipeline.py` and `formatting_transfer.py` may emit formatting-diagnostics artifacts because they own the failure contexts, but cleanup/retention policy for `.run/formatting_diagnostics` should be centralized behind one helper boundary rather than duplicated in both modules.
- `scripts/_shared.ps1` remains the owner of `project.log` lifecycle, and `scripts/project-control-wsl.sh` remains the owner of `streamlit.log` lifecycle, but both should follow one documented retention/config contract rather than inventing unrelated policies.
- Optional `.run` guardrails, if implemented, should have one Python-side owner for pruning order and file-classification policy; callers should invoke that owner rather than embed pruning heuristics inline.

### 6.2 Single-source-of-truth rule for policy values

- `DOCX_AI_LOG_LEVEL` is the canonical example for this wave: one documented runtime variable with one parsing boundary.
- If additional retention knobs are introduced for `.run` hygiene, they should follow the same pattern: one documented canonical name per policy value, one parsing boundary per runtime, and one effective default stated in docs.
- Do not scatter default TTLs, size caps, or backup counts across unrelated modules when those values describe one shared operational policy.
- If a policy is intentionally file-family-specific, state that explicitly in docs and helper names so the distinction is architectural rather than accidental.

## 7. Target State

The target is a quieter, bounded, implementation-ready runtime artifact model within the current monolith.

### 7.1 Logging configuration target

- Application log level becomes configurable via environment or config input, with `DOCX_AI_LOG_LEVEL` as the canonical environment variable.
- Supported values should be `DEBUG`, `INFO`, `WARNING`, `ERROR`, and `CRITICAL`, case-insensitive.
- Invalid values should fall back to `INFO` and emit one warning-level startup log entry explaining the fallback.
- `INFO` remains the default unless a later operational decision changes the default explicitly.

### 7.2 Runtime log-shaping target

- High-frequency success-path events that are mostly diagnostic move from `INFO` to `DEBUG`.
- `processing_started` remains visible at `INFO` because it marks run boundaries and key execution inputs.
- `block_started` moves to `DEBUG` by default.
- `block_map` is replaced by a compact summary event at `INFO` and an optional expanded detail event at `DEBUG`.
- Image retry/adaptation/candidate-selection chatter is reduced so `INFO` captures major state transitions and outcomes, while iterative per-attempt details live at `DEBUG`.

### 7.3 Log-file retention target

- `.run/app.log` keeps the existing rotating-file behavior unless tuning is justified during implementation, but its effective write rate drops due to level/config changes.
- `.run/project.log` gains bounded-growth behavior through rotation and retention.
- `.run/streamlit.log` gains bounded-growth behavior during long uptime through a mechanism compatible with stdout/stderr redirection, rather than relying only on startup truncation.
- All `.run` log files remain local plaintext files intended for repository-local diagnostics.

### 7.4 Marker-write target

- `.run/app.ready` remains the liveness marker used by the control flow.
- Writes to `.run/app.ready` become throttled or debounced so healthy steady-state rerenders do not rewrite the file on every fragment cycle.
- Liveness semantics must remain sufficient for `project-control-wsl.sh` checks; the contract is freshness within a bounded interval, not per-frame precision.
- With the current `run_every=1` fragment cadence, a 10-30 second freshness window should reduce app-ready writes by roughly 10x-30x during steady-state uptime.

### 7.5 Diagnostics-retention target

- `.run/formatting_diagnostics` gains explicit cleanup and retention rules.
- The policy preserves recent/current-run artifacts for debugging, while preventing indefinite accumulation.
- Production runtime cleanup must never remove `tests/artifacts/...` outputs.

### 7.6 Optional `.run` guardrails target

- The repository may optionally enforce a total-size or total-count budget for `.run` as a final defensive layer.
- Guardrails should be soft and predictable: preserve newest/highest-value artifacts first and prune low-priority older files.
- Guardrails must never delete files needed by the currently active process instance.

### 7.7 Ownership target

- The implementation should converge toward one explicit owner map for runtime-artifact behavior rather than spreading policy across call sites.
- If shared Python-side artifact logic becomes non-trivial, introduce one focused helper module or boundary for `.run` artifact policy instead of extending `app.py`, `document_pipeline.py`, and `formatting_transfer.py` independently.
- Event-producing modules should describe *what happened* and provide artifact payloads; artifact-policy helpers should decide *how long to keep artifacts*, *when to prune them*, and *which files are protected*.
- Cross-runtime log files may still be implemented in different languages, but their thresholds and retention semantics should come from one documented contract.

## 8. Prioritized Workstreams

### P0 - Reduce hot-path write pressure and add bounded retention

Objective: remove the biggest write-volume sources and unbounded log growth without changing architecture.

### P0.1 Configurable application log level

Files in scope:

- `logger.py`
- `README.md`
- relevant tests under `tests/`

Tasks:

- add `DOCX_AI_LOG_LEVEL` parsing in `logger.py` with a narrow supported-value map;
- keep `INFO` as the default when the variable is absent;
- on invalid configuration, fall back safely to `INFO` and record one warning-level message;
- document the environment variable in the main runtime docs.

Acceptance criteria:

- setting `DOCX_AI_LOG_LEVEL=DEBUG` causes debug events to be written to `.run/app.log`;
- leaving the variable unset keeps current default behavior at `INFO`;
- invalid values do not crash startup and resolve to `INFO` with one visible warning;
- tests verify parsing and fallback behavior without depending on global machine config.

### P0.2 Reduce hot-path INFO logging in document and image processing

Files in scope:

- `document_pipeline.py`
- `image_generation.py`
- tests covering log behavior where practical

Tasks:

- keep run-boundary and important failure/success events at `INFO` or above;
- move block-level per-iteration chatter such as `block_started` to `DEBUG`;
- review image retry/adaptation/image-candidate paths and move per-attempt detail logs to `DEBUG` unless they represent a user-visible degradation or terminal fallback;
- preserve warning/error visibility for fallback, retry exhaustion, empty output, and similar abnormal states.

Acceptance criteria:

- for a successful non-image 10-block document run, document-pipeline `INFO` records are reduced by at least 50% relative to the current baseline;
- a failing run still emits enough `INFO`/`WARNING`/`ERROR` context to diagnose the stage and outcome;
- tests or targeted inspection confirm that block-by-block noise no longer appears at `INFO` by default.

### P0.3 Replace verbose `block_map` payload with compact summary plus optional debug detail

Files in scope:

- `document_pipeline.py`
- tests for emitted context shape

Tasks:

- replace the current full `block_map` event that logs every block preview with a compact summary at `INFO`;
- summary should include document-level counts and bounded aggregate metrics such as block count, total target chars, min/max/avg target chars, and optionally the first N block sizes;
- if detailed per-block diagnostics remain useful, emit them only at `DEBUG`, preferably with sampling or preview truncation rules;
- ensure no default `INFO` event serializes the entire block list for large documents.

Acceptance criteria:

- default `INFO` logs no longer contain full block preview arrays;
- `DEBUG` mode still permits engineers to inspect per-block detail when needed;
- log payload size for large processing plans is bounded and visibly smaller than the current `block_map` event.

### P0.4 Add rotation and retention for `.run/project.log`

Files in scope:

- `scripts/_shared.ps1`
- documentation for runtime logs

Tasks:

- replace append-only behavior with a simple local rotation policy;
- preferred shape: primary `project.log` plus numbered backups with size-based rollover and bounded backup count;
- keep implementation PowerShell-native and compatible with concurrent read access expectations similar to the current file-open mode;
- because `Append-ProjectLogEntry()` currently opens the file with `FileShare::ReadWrite`, perform rollover only at a safe lifecycle point or via an atomic-enough rename-and-reopen pattern that does not make concurrent append behavior ambiguous;
- ensure startup/stop/status scripts continue to append without user-visible breakage.

Acceptance criteria:

- `.run/project.log` no longer grows without bound across repeated script usage;
- once the configured threshold is crossed, older content rolls into retained backup files;
- backup count is bounded and oldest backups are removed automatically;
- documentation states the retention policy explicitly.

### P0.5 Bound `.run/streamlit.log` growth during long uptime

Files in scope:

- `scripts/project-control-wsl.sh`
- runtime log docs

Tasks:

- keep startup truncation, but add in-process bounded growth during long runs;
- acknowledge the current constraint: `nohup ... >> "$STREAMLIT_LOG_PATH" 2>&1` cannot be rotated in place by renaming the active file without process-cooperative redirection changes;
- acceptable implementations therefore include a script-controlled bounded writer path, a predictable rollover strategy that preserves the active sink path, or a lightweight periodic size-check mechanism coordinated by the shell entrypoint rather than a naive rename-only scheme;
- avoid a design that requires external system packages or long-running sidecar daemons.

Acceptance criteria:

- a single long-lived Streamlit session does not allow `.run/streamlit.log` to grow without bound;
- current start/stop/status flows continue to work with no new external dependency;
- the active log remains readable through existing log-tail workflows.

### P0.6 Throttle or debounce `.run/app.ready` writes

Files in scope:

- `app.py`
- one focused runtime-artifact helper boundary if extraction is needed
- tests if marker-writing logic is extracted to a helper

Tasks:

- keep `.run/app.ready` as the readiness contract;
- change `_mark_app_ready()` so it only rewrites the file when an in-memory last-write timestamp is older than a configured freshness window;
- use a small, explicit interval such as 10-30 seconds rather than per-frame writes;
- avoid a filesystem-`mtime`-driven throttle check on every frame, because that adds a `stat()` call to the hot path and still provides no meaningful atomicity advantage for this marker;
- tolerate benign duplicate writes under rare concurrent fragment timing; correctness here is freshness, not strict single-writer semantics;
- if the helper logic grows beyond a few lines, move the throttle state/mechanics behind one runtime-artifact helper so `app.py` remains orchestration-only;
- keep the implementation lightweight enough for fragment paths.

Acceptance criteria:

- steady-state fragment rerenders do not rewrite `.run/app.ready` every second;
- the file timestamp still advances frequently enough for runtime status checks to treat the app as healthy;
- implementation does not add heavy file scanning or blocking operations to `_finalize_app_frame()`.

### P1 - Formalize artifact retention and `.run` hygiene

Objective: extend bounded-growth behavior from logs to auxiliary diagnostics artifacts.

### P1.1 Add retention and cleanup for `.run/formatting_diagnostics`

Files in scope:

- `document_pipeline.py`
- `formatting_transfer.py`
- one shared retention/helper boundary for formatting diagnostics
- tests for cleanup/discovery behavior
- relevant docs

Tasks:

- define a retention policy for `.run/formatting_diagnostics` using TTL, count cap, size cap, or a combination;
- recommended baseline policy: preserve artifacts for the current run plus a bounded recent history, e.g. max age 7 days or max count 100, with pruning of oldest files first whenever either threshold is exceeded;
- run cleanup at a low-frequency safe point such as artifact write time or process-start boundary, not on every UI frame;
- keep artifact emission in the pipeline modules, but route pruning/retention decisions through one shared helper so both emitters follow the same rules;
- preserve compatibility with validation tooling that discovers current-run or recent artifacts, and with `document_pipeline.py:_collect_recent_formatting_diagnostics()` which scans the same directory.

Acceptance criteria:

- `.run/formatting_diagnostics` cannot grow indefinitely under repeated processing runs;
- current-run artifacts remain discoverable by existing or updated validation helpers;
- tests cover pruning order and confirm that only `.run/formatting_diagnostics` is affected;
- documentation distinguishes runtime diagnostics retention from `tests/artifacts/...` retention.

### P1.2 Separate production runtime artifacts from dev/test artifacts by contract

Files in scope:

- this spec's follow-up documentation targets such as `README.md` and validation docs

Tasks:

- document that `.run/` is the production-like local runtime artifact area subject to rotation/retention;
- document that `tests/artifacts/...` holds validation/dev artifacts and is not cleaned by runtime retention logic;
- ensure any helper names or cleanup functions reflect that scope boundary clearly.

Acceptance criteria:

- docs explicitly state which directories are runtime-managed and which are validation-managed;
- no runtime cleanup path walks into `tests/artifacts/...`;
- test names and helper names make the boundary obvious.

### P2 - Add optional `.run` guardrails and operational polish

Objective: provide a final safety net after primary fixes are in place.

### P2.1 Optional total-size and count guardrails for `.run`

Files in scope:

- one shared runtime-artifact helper boundary if guardrails are enabled
- `logger.py`, `document_pipeline.py`, `formatting_transfer.py`, `scripts/*` as integration points
- tests/documentation

Tasks:

- add optional global guardrails such as `DOCX_AI_RUN_DIR_MAX_MB` and/or `DOCX_AI_RUN_DIR_MAX_FILES`;
- when thresholds are exceeded, prune oldest low-priority artifacts first, preserving active/current markers and freshest logs;
- define explicit priority ordering so pruning is deterministic.
- keep the pruning policy centralized; callers may trigger guardrail evaluation, but they should not each define their own deletion order.

Recommended deletion priority if implemented:

1. old `.run/formatting_diagnostics/*.json`
2. rotated `project.log.*` / `streamlit.log.*` / `app.log.*`
3. stale marker-style files that are known to be regenerable
4. never active process PID files, current primary logs, or the newest readiness marker state needed by running scripts

Acceptance criteria:

- when enabled, `.run` remains within an approximately bounded footprint after cleanup settles;
- pruning is deterministic and documented;
- guardrails are optional and disabled by default unless explicitly configured.

### P2.2 Operational observability polish

Files in scope:

- runtime docs
- selective test coverage

Tasks:

- document how to temporarily raise verbosity for debugging and how retention behaves for each `.run` artifact type;
- optionally emit one startup summary line describing effective log level and retention settings;
- ensure docs explain how to inspect recent formatting diagnostics after retention is introduced.

Acceptance criteria:

- engineers can determine the effective runtime logging/retention mode from docs and runtime inspection;
- no hidden retention behavior remains undocumented.

## 9. Acceptance Criteria

This spec is complete only when all of the following are true.

1. `DOCX_AI_LOG_LEVEL` is supported, tested, and documented.
2. Default `INFO` logs are materially quieter than the current baseline for successful long document runs; at minimum, for a successful non-image 10-block document run, document-pipeline `INFO` records are reduced by at least 50% relative to the current baseline because full `block_map` payload logging and per-block `block_started` logging no longer occur at `INFO`.
3. `block_map` no longer emits full block-preview arrays at default `INFO` verbosity.
4. `.run/project.log` has explicit rotation/retention and cannot grow indefinitely.
5. `.run/streamlit.log` remains bounded during a single long uptime, not only across restarts.
6. `.run/app.ready` writes are throttled or debounced, with health checks still functioning.
7. `.run/formatting_diagnostics` has explicit retention/cleanup behavior with tests covering pruning logic.
8. Runtime cleanup affects `.run/` only and does not clean `tests/artifacts/...`.
9. The implementation preserves the current monolith and WSL-first operational contract.
10. No shared runtime-artifact policy value is hard-coded independently in multiple production call sites without one documented contract.
11. `app.py` remains orchestration-focused and does not become the owner of non-trivial retention or pruning logic.

## 10. Verification Plan

Verification should combine targeted unit tests, integration-style inspection, and documentation review.

### 10.1 Automated tests to add or update

- `tests/test_logger.py` or equivalent:
  - valid `DOCX_AI_LOG_LEVEL` parsing;
  - invalid-value fallback to `INFO`;
  - `DEBUG` events emitted only when enabled.
- `tests/test_document_pipeline.py`:
  - compact block-summary event shape;
  - absence of full `block_map`-style payload at default `INFO` behavior;
  - preservation of failure-path logging.
- `tests/test_formatting_transfer.py` and/or `tests/test_document.py`:
  - formatting diagnostics retention helper behavior;
  - pruning by age/count while preserving newest artifacts.
- script-focused tests where feasible, or inspection-friendly helper coverage for log rotation decisions in `scripts/_shared.ps1` and `scripts/project-control-wsl.sh`.
- helper-level tests if app-ready throttling is extracted from `app.py` into a deterministic function.

### 10.2 Manual inspection steps

- run the app with default settings and verify `.run/app.log` does not contain per-block `INFO` chatter for a normal successful job;
- run with `DOCX_AI_LOG_LEVEL=DEBUG` and verify detailed pipeline events reappear;
- confirm repeated script usage rotates `.run/project.log` as documented;
- keep a dev session alive long enough to verify `.run/streamlit.log` rollover or bounded growth during uptime;
- inspect `.run/app.ready` timestamp progression over time and confirm it updates on a throttle interval rather than every fragment cycle;
- generate multiple formatting diagnostics artifacts and verify pruning policy preserves current/recent entries only.

### 10.3 Documentation updates required

- update `README.md` with `DOCX_AI_LOG_LEVEL` and runtime log-retention notes;
- update any runtime-control or workflow docs that describe `.run` behavior;
- if validation docs mention formatting diagnostics discovery, update them to note bounded retention in `.run` and the separate status of `tests/artifacts/...`.

## 11. Risks and Mitigations

- Reduced `INFO` logging may hide signals engineers currently rely on during ad hoc debugging.
  - Mitigation: keep run-boundary and abnormal-state events at `INFO`/`WARNING`, and make deep detail recoverable via `DOCX_AI_LOG_LEVEL=DEBUG`.
- Over-aggressive retention could remove artifacts needed for current-run diagnosis.
  - Mitigation: preserve newest artifacts, preserve current-run outputs, and clean only at safe lifecycle points.
- Streamlit log rotation could interfere with existing tail/read workflows if implemented carelessly.
  - Mitigation: keep primary active log path stable and rotate to predictable numbered backups.
- App-ready throttling could create false negatives in health checks if the interval is too long.
  - Mitigation: choose a bounded freshness window shorter than status-check expectations and verify with runtime inspection.
- Script-level rotation implemented separately from Python logging could create inconsistent policies.
  - Mitigation: document per-file policy explicitly and keep thresholds simple and local rather than pretending there is one shared hidden engine.
- `.run` guardrails, if enabled, could prune the wrong files.
  - Mitigation: make guardrails optional, deterministic, priority-based, and well-tested before default adoption.

## 12. Rollout Notes

- Implement P0 first; it delivers the largest write-volume reduction with the lowest architectural risk.
- P1 should follow once default log volume is reduced, so diagnostics retention can be tuned against the quieter steady-state baseline.
- P2 guardrails should remain optional until real usage confirms the primary fixes are insufficient.
- Changes should be delivered in small slices so log-shape regressions and validation-artifact expectations can be reviewed independently.
- No rollout step should require a new service, system package, or departure from the current WSL-first developer workflow.
