# Feature Specification: Per-run artifact isolation and confined restart-source deletion

Date: 2026-07-15
Status: **PLANNED (Wave 1 / S2).** Correctness + safety. Two related filesystem defects in the run-artifact layer:
non-unique artifact naming (cross-run overwrite) and unconfined file deletion trusting persisted metadata.
Owner surface: `runtime/artifacts.py` (`_build_ui_result_stem`, `write_ui_result_artifacts`,
`write_structure_manifest_artifact`), `processing/restart_store.py` (`clear_restart_source`).
Companion: prerequisite for multi-user hosting — under a single local user collisions are rare; under concurrency
they become cross-tenant overwrite and path-traversal.

## Problem A — artifact collisions (verified against HEAD d27c137)

[artifacts.py:46-50](/D:/www/Projects/2025/DocxAICorrector/src/docxaicorrector/runtime/artifacts.py#L46-L50) builds the
artifact stem from only a second-granularity timestamp plus the sanitized source stem:

```python
timestamp = time.strftime("%Y%m%d_%H%M%S", ...)
return f"{timestamp}_{stem}.result"
```

All sessions write into the shared `.run/ui_results/` dir (`UI_RESULT_ARTIFACTS_DIR = RUN_DIR / "ui_results"`), and
every derived artifact (`.md`, `.docx`, `.tts.txt`, `.meta.json`, `.manifest.json`, `.formatting_review.txt`) shares
this stem via plain `write_text`/`write_bytes` (overwrite semantics). There is no `run_id`/`session_id`/uuid/pid in
the name. Two runs of the same source filename within the same wall-clock second overwrite each other's whole
artifact group. The same pattern recurs in `write_structure_manifest_artifact` (`{timestamp}_{stem}.segments.json`).
Writes are also non-atomic: a crash mid-write leaves a partial artifact that reads as delivered.

## Problem B — unconfined restart-source deletion (verified)

[restart_store.py:90-101](/D:/www/Projects/2025/DocxAICorrector/src/docxaicorrector/processing/restart_store.py#L90-L101)
`clear_restart_source()` reads `storage_path` from the dict and `unlink()`s it with only `exists()`/`is_file()`
guards — no containment check that the path is inside `RUN_DIR`, no `restart_*`/`completed_*` filename check. The
sibling `cleanup_stale_persisted_sources()` already enforces both (`RUN_DIR.glob("*_*")` + prefix filter), so the
codebase knows the pattern; this function skips it. Today the dict is internally produced, so exposure is bounded;
with externally-restorable session metadata or a corrupted session state it becomes arbitrary file deletion.

## Scope (planned)

1. **Unique run id in the stem.** Add a short opaque `run_id` (e.g. 6–8 hex chars derived once per run) to
   `_build_ui_result_stem` and `write_structure_manifest_artifact` → `{timestamp}_{stem}_{run_id}.result`. The id is
   generated once per run and threaded through so every artifact in a group shares it. Prefer deriving the id from
   existing per-run context (prepared-source key / job id) where available; fall back to `uuid4().hex[:8]`.
2. **Atomic group write.** Write each artifact to a temp file in the same dir and `os.replace` into place, so a
   crash never leaves a half-written `.md`/`.docx`/manifest that downstream treats as complete.
3. **Confine `clear_restart_source`.** Before `unlink`, resolve the path and require: (a) it is inside `RUN_DIR`, and
   (b) its name matches `restart_*`/`completed_*`. On mismatch, log a warning event and return without deleting.
   Factor the check so it and `cleanup_stale_persisted_sources` share one predicate.

## Test plan

- Two `_build_ui_result_stem` calls with the same source name and `created_at` within the same second produce
  DIFFERENT stems (run_id differs). Artifacts from two runs coexist in `.run/ui_results/` with no overwrite.
- Atomic write: no `.tmp`/partial file remains after a successful write; a simulated failure mid-write leaves the
  prior artifact intact (no truncated final file).
- `clear_restart_source` deletes a valid `restart_*` file inside `RUN_DIR`; refuses (and warns, does not raise) a
  path outside `RUN_DIR` and a non-matching name inside `RUN_DIR`.

## Out of scope

- Introducing real per-user identity or a user-scoped directory tree (arrives with the backend; run_id is the
  minimal isolation primitive that composes with it later).
- Retention-policy changes beyond keeping current pruning working with the new stem.

## SaaS rationale

`run_id` in the stem is the seam that later becomes user/session scoping; confined deletion removes a
path-traversal/data-loss vector that turns critical the moment persisted metadata can cross a trust boundary.
