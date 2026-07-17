# Feature Specification: Round-8 P1 completion — tenant cache identity contract + caption-heading conflict blocks delivery

Date: 2026-07-17
Status: **PLANNED (2026-07-17).** Round-8 verified that two round-7 fixes (spec 041 P1-1 and P1-4) closed
the MECHANISM but not the actual effect: the cache identity is re-derived from config instead of the
injected factory, and the caption→heading acceptance-verdict failure never gates delivery. Both confirmed
against live code by the orchestrator. Owner decision on the identity contract: **Explicit-or-bypass**
(A below). Merge stays not-recommended until both land.

## P1-A — ProcessingService must NOT re-derive the injected factory's cache identity from config

**Verified:** `processing_service.py:371-388` computes `prepare_client_cache_identity =
resolve_prepared_cache_client_identity(app_config)` — derived from `app_config`/env ONLY. The injected
`_prepare_client_factory` closes over `deps.get_client_fn` / `deps.get_client_for_model_selector_fn`, which
can be tenant-specific. Two tenant factories with the SAME `app_config`/env but different
endpoints/credentials therefore collapse to the SAME identity → one shared-cache key → cross-tenant reuse.
The spec-041 test only exercised hand-passed `idA/idB`, not the real ProcessingService wiring.
`ProcessingServiceDependencies` (`:68`) exposes no tenant identity today.

**Fix — Explicit-or-bypass (owner-chosen contract):**
- Add an optional tenant-identity to the dependency contract: `ProcessingServiceDependencies` gains
  `client_cache_identity: str | None = None` (an opaque, secret-safe fingerprint the tenant
  factory/dependency supplies for the client it actually resolves).
- In `run_prepared_background_document`: REMOVE the `resolve_prepared_cache_client_identity(app_config)`
  re-derivation. Pass `client_cache_identity=deps.client_cache_identity` into the
  `prepare_document_for_processing(...)` injection. When it is None (no tenant identity supplied) and a
  factory is injected with AI review on, the ALREADY-IMPLEMENTED preparation primitive
  (`preparation.py:1067-1103`) bypasses the SHARED cache for the run (per-session tier stays active) — the
  safe default, no false guarantee.
- Drop the now-unused `resolve_prepared_cache_client_identity` import from `processing_service.py` if
  nothing else there uses it. Keep the function in `preparation.py` (the config-default path and the
  single-tenant UI factory legitimately use the config-derived identity — the UI is not a tenant factory).
- Do NOT change the UI path (`ui/_app.py` `_build_preparation_client_factory`): it is single-tenant, so a
  config-derived identity IS the tenant identity there — keeping shared-cache reuse is correct.

**Test (real ProcessingService wiring, per reviewer):** drive an actual `ProcessingService` /
`run_prepared_background_document` with two dependency sets that share `app_config` but carry DIFFERENT
`client_cache_identity` values → run A primes, run B (different identity) MISSES, run A again HITS. And:
deps with `client_cache_identity=None` + AI review on → the shared cache is bypassed (a second identical
run does not serve the first's shared entry). Stub the heavy preparation work (reuse
`test_preparation.py`'s counting-builder pattern) so it is fast/deterministic. `tests/test_processing_service.py`.

## P1-B — caption→heading conflict must drive quality_status="fail" so delivery is blocked

**Verified:** spec-041 P1-4 made the ACCEPTANCE VERDICT fail on a caption→heading conflict
(`acceptance.py:618-626`), but `late_phases.py:636-646` only WRITES the verdict into `quality_report`;
the terminal branches gate on `quality_report["quality_status"]` (`:647` warn, `:664` fail), NOT on the
verdict. `quality_gate.py` records the conflict only as a metric (~1208/1727). So with `quality_status !=
"fail"`, primary UI artifacts + `.result.*` still publish (`late_phases.py:1056-1125`) despite a failed
acceptance verdict. The `quality_gate.py:1116-1119` comment claiming the conflict "gates unconditionally"
is therefore currently FALSE for delivery.

**Fix:** in the quality-report assembly (`quality_gate.py`, where the caption→heading conflict count is
computed/recorded — grep `caption_heading_conflict`), when the conflict count > 0, promote it to a gate
FAILURE via the existing mechanism: either `_apply_quality_gate_reason(quality_status, gate_reasons,
reason="caption_heading_conflict", fatal=True)` (`:128`) or add `"caption_heading_conflict"` to
`_FATAL_DOCUMENT_GATE_REASONS` (`:184`) and emit the reason — so `quality_status` becomes `"fail"` and a
`gate_reasons` entry is present. This routes into the EXISTING `late_phases.py:664` fail path, which does
not publish primary artifacts. Provide a human-readable reason string (extend
`humanize_quality_gate_reasons` if needed). Update the `quality_gate.py:1116-1119` comment so it is
accurate (the conflict now gates delivery via `quality_status="fail"`, and the acceptance verdict's
`caption_heading_conflict_absent` check remains the auditable record).

**Test:** `finalize_processing_success` (or the smallest late-phase slice) with a formatting diagnostic
carrying a caption→heading conflict → `quality_status == "fail"`, a `caption_heading_conflict` gate reason
present, and primary UI artifacts / `.result.*` are NOT written (delivery blocked). Zero conflicts →
publishes normally. Unmapped coverage stays ADVISORY (never forces fail). `tests/test_late_phases_*` +
`tests/test_real_document_pipeline_validation.py`.

## Non-goals

- NO change to the unmapped-coverage advisory behavior (specs 038/039 — review data, never gates).
- NO change to the single-tenant UI cache identity (config-derived is correct there).
- NO new per-book literals; the conflict signal is the general caption↔heading structural detector already
  computed.

## Anti-regression

- P1-A: config-default path (no injected factory) unchanged (spec-040 config identity + shared cache);
  AI-review-off keeps shared caching; the real-ProcessingService isolation test above passes; existing
  `test_processing_service.py` / `test_preparation.py` stay green.
- P1-B: a run with NO caption→heading conflict still publishes (quality_status unchanged); a genuine
  unmapped-coverage tail does NOT force fail (advisory); the golden `acceptance_verdict_clean.json` is
  unaffected (no conflict on the clean fixture).
- Full no-LLM suite green; pyright ≤246; CI green (watched).

## SaaS rationale

Closes the real cross-tenant reuse path honestly (no config-derived false guarantee; unknown identity →
safe shared-cache bypass), and makes a genuine caption→heading structural defect actually BLOCK delivery in
production instead of merely being recorded in a verdict nobody gates on.
