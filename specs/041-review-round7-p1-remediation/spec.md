# Feature Specification: Round-7 P1 remediation — tenant cache identity, cancellable admission, evidence/acceptance order, independent caption-heading gate

Date: 2026-07-17
Status: **PLANNED (2026-07-17).** Four verified round-7 P1 findings (each confirmed against live code by
the orchestrator before planning). All four are correctness/isolation defects; two (#1, #4) are gaps in
prior specs 040 / 038 that this spec closes honestly. Merge of PR #4 is NOT recommended until these land.
"Rejected as overengineering" items (atomic restart-source write, extra PDF pixel guard, quality-gate
private-import seam) are intentionally OUT of scope.

## P1-1 — Preparation cache must isolate the actually-injected tenant client_factory

**Verified:** `preparation.py:1021-1025` calls `_resolve_prepared_cache_client_identity(resolved_config,
ai_review_effective_enabled, ai_review_model)` — the identity is derived from config/env ONLY; the injected
`client_factory` (`prepare_document_for_processing` param, `:969`) is NOT reflected. Two callers with the
SAME `app_config`/env but DIFFERENT factories/credentials collide on one `_shared_preparation_cache`
(`:782`, process-global) entry, so tenant B can read tenant A's AI-boundary-review result. Spec 040's test
(`test_preparation.py:1441-1499`) exercises the helper/key by hand, not the real two-factory entrypoint.
This is the spec-040 CONFLICT ("fingerprint the client that is actually used").

**Fix (minimal, per reviewer):**
- `prepare_document_for_processing` gains `client_cache_identity: str | None = None` (a caller-supplied,
  secret-safe fingerprint of the injected factory's tenant identity).
- Shared-cache use for the AI-review-dependent prepared document is gated:
  - `client_factory is None` (config-default path) → keep the existing config-derived identity
    (`_resolve_prepared_cache_client_identity`) — the client IS config-derived there, so it is authoritative.
  - `client_factory` injected AND `ai_review_effective_enabled` AND `client_cache_identity` provided →
    fold that identity into the key (shared cache is safe: distinct identities → distinct keys).
  - `client_factory` injected AND `ai_review_effective_enabled` AND NO `client_cache_identity` → DO NOT use
    the shared cache for this run (skip shared read AND shared store); the per-session cache
    (session-scoped, already tenant-safe) may still serve. This is the safe default — never serve a
    client-dependent artifact across an unknown-identity boundary.
  - `ai_review_effective_enabled` False → client does not shape the artifact → shared cache safe (identity "").
- The injecting callers (`processing_service.py` `_prepare_client_factory`, `ui/_app.py`
  `_build_preparation_client_factory`) compute the secret-safe identity for their tenant factory (reuse the
  spec-040 fingerprint logic — provider selector + base_url + api_key_env + sha256(secret) via
  `resolve_model_selector`/`get_provider_config` + `load_project_dotenv`) and pass it as
  `client_cache_identity` alongside `client_factory`.

**Test (real entrypoint, not the helper):** drive `prepare_document_for_processing` itself — tenant A (factory
+ identity A) primes; tenant B (different factory + identity B, same app_config/token) MISSES; tenant A again
HITS. Plus: factory injected + AI review on + identity None → shared cache NOT used (a second run does not
serve the first's shared entry). Reset `_shared_preparation_cache` between cases.
**Verify:** `bash scripts/test.sh tests/test_preparation.py -vv`.

## P1-2 — Processing admission wait must be cancellable

**Verified:** `processing_runtime.py:1966-1974` `_admission_guarded_worker_target` does a raw blocking
`_PROCESSING_ADMISSION_GATE.acquire()` with no timeout / no `stop_event`. If the gate is full, Stop during the
wait does not cancel; once a slot frees, `worker_target` runs anyway. The cancellable primitive already
exists and is used by the preparation path: `_acquire_admission_slot_cancellable(gate, stop_event,
poll_seconds)` (`:144-161`, returns False on cancel and the caller must NOT release).

**Fix (mirror the preparation path):** replace the raw acquire with
`_acquire_admission_slot_cancellable(_PROCESSING_ADMISSION_GATE, stop_event)`. On `False` (cancelled): emit
the normal stopped completion (a `WorkerCompleteEvent(outcome="stopped")` / the same stopped signal the
preparation path uses at `:2149-2160`) and return WITHOUT running `worker_target` and WITHOUT releasing
(nothing was acquired). On `True`: run `worker_target` in `try/finally` with `release()` on every exit path
(unchanged). Thread the worker's `stop_event` into the guarded target.

**Test:** admission gate saturated; Stop set before a slot frees → `worker_target` is never invoked, the run
surfaces `stopped` to the UI, and the semaphore is not over-released.
**Verify:** `bash scripts/test.sh tests/test_processing_runtime.py -vv`.

## P1-3 — Real-document harness: load cleanup evidence BEFORE building the acceptance verdict

**Verified:** `run_lietaer_validation.py:5633-5640` calls `evaluate_lietaer_acceptance(report, …)` while
`report["reader_cleanup_evidence"]` is still unset — it is only attached at `:5641-5646`. So the
`reader_cleanup_stage_completed` check (`acceptance.py:415-430`) sees an empty `stage_status`, which passes
(`not status or status == "completed"`), even when the real cleanup stage `stage_status == "failed"`. The
stale verdict then drives `final_status` (`:5734-5739`).

**Fix:** load `reader_cleanup_evidence` (and merge its artifact paths) and attach it to `report` BEFORE the
`evaluate_lietaer_acceptance` call, so the verdict evaluates the real cleanup status. If any later verifier
mutation feeds acceptance inputs, rebuild the verdict after it. Keep all other harness behavior.

**Test:** a narrow canonical test driving the harness (or the acceptance-input assembly) with a cleanup report
`stage_status="failed"` MUST yield a failed acceptance / non-completed final status.
**Verify:** targeted test in `tests/test_real_document_pipeline_validation.py`; then a developer-scheduled real
run.

## P1-4 — Caption→heading conflict must be an independent hard gate (applicable in production)

**Verified:** `acceptance.py:562-599` `formatting_diagnostics_threshold` sets
`passed=bool(total_caption_heading_conflicts == 0)` but `applicable=mismatch_threshold is not None`.
Production resolves `mismatch_threshold=None` (`quality_gate.py:1107-1129`, keys absent from config.toml;
`late_phases.py:636-645` calls the verdict), so the check is NON-applicable in production and the roll-up
ignores it (`failed_checks = [c for c if c.get("applicable", True) and not c["passed"]]`). A genuine
caption→heading structural conflict therefore publishes GREEN. This is the spec-038 CONFLICT (038:56-63
promised a hard caption/heading gate).

**Fix:** emit a SEPARATE `caption_heading_conflict_absent` check that is APPLICABLE whenever formatting
diagnostics are present (independent of `mismatch_threshold`): `passed = total_caption_heading_conflicts ==
0`, `applicable = len(formatting_diagnostics) > 0` (or diagnostics were computed), carrying the conflict
count/examples. Keep `formatting_diagnostics_threshold` as-is otherwise (its unmapped-coverage side stays
advisory per specs 038/039). Update the stale comments that say a configured `0` "still gates"
(`acceptance.py:390-400`, `quality_gate.py:1111-1115`) to clarify: unmapped coverage is ADVISORY (specs
038/039); the caption/heading structural conflict gates unconditionally via the new check. Update
`specs/038-coverage-is-review-data-neutralize-gate/spec.md` (the caption/heading-gate wording) to reference
the independent check.

**Test:** production `build_report_acceptance_verdict` (default config, `mismatch_threshold=None`) with a
caption→heading conflict MUST fail (`caption_heading_conflict_absent` in `failed_checks`); with zero
conflicts it passes; unmapped coverage stays advisory (not in `failed_checks`). Regenerate the golden
`acceptance_verdict_clean.json` (additive; clean run has 0 conflicts → check present, passed, not failing).
**Verify:** targeted acceptance/late-phase canonical test.

## Non-goals / excluded (reviewer "overengineering", owner-aligned)

- NO atomic restart-source write (narrow crash/disk window; restart cache, not user-visible output).
- NO extra PDF embedded-image pixel guard (decode-before-existing-budget path not confirmed).
- NO quality-gate private-import seam change (documented; no proven bug-risk).

## Anti-regression (all four)

- Existing `tests/test_preparation.py`, `test_processing_runtime.py`, `test_real_document_pipeline_validation.py`,
  `test_application_flow.py`, `test_late_phases_characterization.py` stay green; golden
  `acceptance_verdict_clean.json` regenerated additively (run-level `passed`/`failed_checks` unchanged for the
  clean fixture); pyright ratchet ≤246; full no-LLM suite green; CI green.
- #1: config-default path (no factory) keeps byte-identical keys (spec-040 behavior preserved); AI-review-off
  keeps shared caching.
- #2: the non-cancelled path is behavior-identical (acquire → run → release); no semaphore over-release on any
  path (BoundedSemaphore would raise on double-release — assert it does not).
- #4: unmapped coverage remains advisory (Constitution VII); only the NEW independent check gates caption/heading.

## SaaS rationale

Closes a real cross-tenant reuse path (#1), makes Stop honor the admission wait so a queued run is truly
cancellable (#2), restores the real-document gate's integrity so a failed cleanup cannot publish green (#3),
and makes a genuine structural defect fail in PRODUCTION instead of only in the test harness (#4).
