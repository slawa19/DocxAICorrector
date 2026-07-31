# Feature Specification: Round-12 pre-merge remediation of the round-10/11 branch

Date: 2026-07-31
Status: **IMPLEMENTED (2026-07-31) — merged to `main` via PR #6.** Round-12 is a verification round
over `fix/round10-specs-044-048-remediation` (specs 044–050), which had been pushed on 2026-07-20…22
but never opened as a PR — so **CI had never run on it** and the round-11 commits (`c5cdab0`,
`2d9d8be`) had never been reviewed by anyone. Four independent verifiers (behavioural proof,
blast-radius, build quality, adversarial) ran against the branch; the orchestrator re-verified every
P1 against live code before acting. One **P1 regression introduced by round-11** and four P2s were
found and fixed here; the P3 tail is recorded below as deliberate, unfixed residue.

## Why this round exists (process finding)

The branch's own commit messages claimed "Full suite green (2264 passed, 14 skipped); pyright ratchet
held at 196". Measured on a clean tree in WSL: **2268 passed, 9 skipped** — the claimed numbers came
from a dirty tree without system dependencies. And "ratchet held at 196" was misleading: the baseline
was *lowered* 246→196 by 55 fixes, which **masked 5 genuinely new pyright errors** the branch
introduced. The lesson from spec 041 repeats: to locate a ratchet delta, diff the *sorted error lists*
of both trees — never trust what the ratchet prints.

## P1 — a crash after delivery destroyed the already-delivered result (regression from `c5cdab0`)

**Verified flow.** Round-11 F3 correctly observed that a crash mid-run could leave deliverable bytes
with no disposition, which `build_result_bundle` defaults to `"accepted"` — a green success view under
a red error. Its fix (`processing/processing_service.py:322-337`) cleared `latest_docx_bytes`,
`latest_narration_text` and `latest_delivery_disposition` on **any** exception escaping
`run_document_processing`.

But `finalize_processing_success` continues to execute after the result is delivered — the `.result.md`
/ `.result.docx` files are written **and verified on disk** and the canonical `ui_result_artifacts_saved`
event is already logged — and that tail was not exception-safe:

- `write_reader_cleanup_diagnostics` was guarded by `except OSError` only, while
  `reader_cleanup_mvp/service.py:692` can raise `KeyError` (missing `markdown_path`) and `:703` can raise
  `TypeError` (`json.dumps` of a non-serialisable report);
- `build_segment_result_records(...)` had **no guard at all**;
- the `ui_audiobook_artifact_saved` log call can raise `KeyError`/`TypeError`/`ValueError`.

Any of these propagates through `pipeline/setup.py` and `_pipeline.py` untouched into the crash handler,
which then nulls the delivery state. **User-visible effect:** a finished `.result.docx` sits on disk,
unreachable — no result block, no download button — and the run is offered as RESTARTABLE, i.e. the user
is invited to pay for a full LLM re-run on top of a completed document. Before `c5cdab0` they saw the
error banner *and* could download the delivered file.

**Fix.**
1. `pipeline/late_phases.py:1295-1399` — every post-delivery secondary write (reader-cleanup diagnostics,
   segment-record build, segment-registry write, audiobook log) catches `Exception` and logs its own
   WARNING, under an outer backstop covering the whole block. Primary persistence
   (`write_ui_result_artifacts` + `_verify_primary_result_artifacts_or_raise`) is untouched and still
   funnels into its existing `primary_artifacts_persisted=False` path.
   `LatePhaseStopped` derives from `BaseException` (`pipeline/contracts.py:13`), so cooperative
   cancellation still propagates through all of these handlers by construction.
2. `processing/processing_service.py:59-92, 357-395` — the crash handler no longer clears delivery state
   unconditionally. `_DeliveryObservingRuntime`, a transparent runtime proxy, records whether the run ever
   emitted `latest_delivery_disposition`; the clearing now applies only when it did not. This preserves
   round-11 F3 exactly: the disposition is emitted at only three points (`late_phases.py:731`, `:982`,
   `:1221`), all of which are genuine delivery decisions, and a mid-run byte emit never sets it — so F3's
   dangerous shape is still detected and still cleared.

**Proof of effect (not mechanism).** With the fix reverted, the new tests fail with the real defect
(`TypeError: registry record is not serialisable` escaping `finalize_processing_success`; worker-level
`assert None == {'status': 'blocked'}`). With the fix: run `succeeded`, both `.result.*` present and
non-empty on disk, `get_current_result_bundle()["docx_bytes"] == b"final-docx"`, disposition `accepted`,
both failures surfaced as WARNINGs carrying `error_type`.

## P2 — losing the formatting-diagnostics evidence scored *perfectly* and said nothing

**Verified flow.** Spec 048 moved diagnostics collection from a time window to ownership
(`run_id` + `source_token`). Round-11 found that a blank `run_id` destroyed the artifact and fixed it by
degrading to `scope="offline"` instead of raising — which removed the **only** signal that anything was
wrong. End to end with a blank identity: the artifact is written offline **silently**;
`collect_owned_formatting_diagnostics` filters it out and returns `[]` **silently**;
`late_phases.py` then sees no diagnostics change, so the post-cleanup rebuild — and with it the
caption→heading delivery gate that spec 043 exists to enforce — never runs; and the canonical gate
computes `formatting_diagnostics_count = 0`, `max_unmapped_* = 0`, so
`formatting_diagnostics_threshold` **PASSES**. Losing the evidence produced the best possible score.
Worse, the new test `test_formatting_diagnostics_wrapper_falls_back_to_offline_on_blank_identity`
asserted the *absence* of the warning — the lost detector was pinned by a test.

`pipeline/support.py` had the mirror defect: it hard-coded `scope="live"`, so a blank identity threw
inside its `try` and the marker diagnostics were **not written at all** — the forensic evidence
disappeared exactly when a block had failed.

Both production entry points do mint identities today (`processing_runtime.py:2033`,
`processing_service.py:433`), so this was latent — but nothing enforced it: `run_document_processing`,
`ProcessingService.run_document_processing` and `run_processing_worker` all declare
`run_id: str | None = None` without validation, and `pipeline/setup.py` silently normalises a missing
value to `""`.

**Fix.**
1. `generation/formatting_diagnostics_retention.py:33-79` — `resolve_owned_diagnostics_scope()` emits
   `formatting_diagnostics_identity_missing` (WARNING, naming which identity is blank) on the live→offline
   downgrade; the offline write is preserved, because explicit replay legitimately has no identity.
   `generation/formatting_transfer.py:161-179` uses it.
2. `pipeline/setup.py:17-56, 196-212` — the normalisation point announces
   `processing_run_identity_missing` through the injected logger (so it reaches both the production log and
   the harness event log). It does **not** raise: offline and replay paths legitimately run without an
   identity, and raising would break the harness.
3. `pipeline/support.py:137-153` — marker diagnostics degrade to offline with the same warning instead of
   vanishing.
4. `validation/structural_checks.py:329-344` — new check `formatting_diagnostics_evidence_not_lost`, the
   anti-fail-open companion to `formatting_diagnostics_threshold`. It does not try to tell the two zeros
   apart by inspecting the zero (impossible, and would rewrite gate semantics); it asks the run, via the
   `processing_run_identity_missing` announcement surfaced as
   `formatting_diagnostics_identity_status` (`validation/structural.py:489-499`). The metric defaults to
   `"complete"` when absent, so clean runs and stub/replay harnesses stay PASSED **by construction** — only
   a run that provably could not claim its own artifacts fails.

**Proof the canonical gate stayed honest:** `scripts/run-real-document-quality-gate.sh` run in full —
**30 passed in 14:55**, including all four `test_corpus_structural_passthrough` books
(mazzucato / lietaer / creatingwealth / money-sustainability).

**Deliberately out of scope (needs its own spec).** `formatting_diagnostics_count` is `0` or `1` (one
canonical payload is selected), while `corpus_registry.toml` sets the thresholds at 5 and 12 — so
`formatting_diagnostics_threshold` **can never fire**. Fixing that means changing both the metric and all
four corpus profiles; it is not a narrow edit and is not attempted here.

## P2 — the underline fix leaked literal markup into the delivered DOCX

`2d9d8be` converted `<u>X</u>` to the pandoc span `[X]{.underline}` without escaping the content. An
unbalanced `]` inside the underlined run breaks the span and the reader sees literal
`[…]{.underline}` in the document. This is reachable on real books: `document/extraction.py` wraps
*every* underlined run in `<u>`, and DOCX splits runs arbitrarily, so an underlined tail like `1]` of
`[1]` (footnote and cross-reference forms) is ordinary.

Measured through real pandoc with the production format
(`markdown+raw_html+superscript+subscript`), reading the resulting OOXML:
`Text <u>a] b</u> more` → **before** `Text [a] b]{.underline} more` (visible garbage) → **after**
`Text a] b more` with the underline applied. `Text <u>]a[</u> more` was even worse before — the `[`
was silently *deleted* from the text.

**Fix.** `generation/_generation.py:33-36, 1171-1213` escapes `\`, `[`, `]` inside the span and
neutralises a preceding `!` or odd backslash run. The underline pass had to move **before** the
super/subscript pass, otherwise escaping would double the synthetic `\ ` that
`_escape_pandoc_script_spaces` emits and kill the superscript role; an ordering guard test pins this.
Balanced cases (`see [1]`, `[прим. 3]`) are unchanged — verified as anti-regression rows, not as
vacuous passes.

## P2 — the config cache silently hollowed out a regression test, and removed env keys went quiet

1. `2d9d8be` added a process-wide `load_app_config()` cache. That made
   `test_load_app_config_emits_legacy_model_warnings_only_once` vacuous: its second call is a cache hit, so
   the loader body — and the deduplication it exists to test — never runs. Proven by mutation: with
   deduplication deleted entirely the old test still **passed**. Fixed by resetting the cache between the
   two calls plus an anti-vacuity guard, and by an autouse reset fixture in `tests/test_config.py`; the
   mutation now fails with `assert 12 == 6`.
2. The branch stopped reading the legacy model env aliases (`DOCX_AI_DEFAULT_MODEL`,
   `DOCX_AI_MODEL_OPTIONS`, `DOCX_AI_VALIDATION_MODEL`, `DOCX_AI_RECONSTRUCTION_MODEL`) but warned only
   about the TOML forms — an operator carrying one of these in `.env` would silently start running a
   different model at a different price. `core/config.py:106-112` and
   `core/config_model_registry.py:331-349` now warn on the env forms too, and the test that pinned the
   silence was inverted.
3. The warning's `replacement` hint was computed as `f"models.{key.removesuffix('_model')}"`, which points
   at `models.validation` / `models.reconstruction` — sections that do not exist. Replacements are now a
   mapping verified against the real `ModelRegistry` roles, with a test that resolves every suggested
   path.

## Build quality

- Full suite on a clean tree, WSL: **2268 → 2296 passed, 9 skipped, 0 failed** (the delta is this round's
  new tests).
- Pyright: **196 → 192**. The 5 errors the branch had introduced under the lowered baseline are fixed by
  proper typing (no `# type: ignore`, no blanket `Any`); one pre-existing error remains in
  `tests/test_processing_service.py`.
- CI coverage gap recorded (not fixed): the workflow deselects `system_deps`, `manual_ai_heavy` and sets
  `DOCXAI_SKIP_WORKFLOW_SMOKE=1`, so **46 of 2296 tests never run in CI**. `static_workflow` *is* covered
  by its own job (the spec-036 F20 finding stays closed), but the list of static files is hard-coded in
  both the workflow and its guard rather than derived from the actual markers — a sixth marked file would
  silently fall out of CI again.

## Anti-regression (mandatory)

1. A non-`OSError` (`KeyError`, `TypeError`) from any post-delivery secondary write leaves the run
   `succeeded`, the bytes downloadable, the disposition intact and both `.result.*` on disk.
2. A crash **before** delivery still clears bytes/narration/disposition (round-11 F3 preserved).
3. A blank `run_id`/`source_token` still writes the artifact offline **and** emits
   `formatting_diagnostics_identity_missing`; marker diagnostics are retained rather than lost.
4. A run that announced a missing identity fails `formatting_diagnostics_evidence_not_lost`, while a clean
   run and a stub harness pass it — the two zeros are distinguishable in the roll-up.
5. Unbalanced brackets inside `<u>` produce clean text plus underline; balanced brackets are unchanged;
   underline nested with super/subscript keeps both roles.
6. Removing the config-warning deduplication makes its test fail; each legacy env alias produces a warning
   whose suggested replacement resolves to a real registry role.

## Not fixed here — deliberate residue

Recorded so the next round does not rediscover them, and so nobody assumes they are closed:

- **P3 `processing/restart_store.py:69`** — the persisted upload is written in place (no tmp + `os.replace`),
  while an integrity mismatch is now a PERMANENT verdict that deletes the record on first read. No reachable
  transient producer was constructed, so this is theoretical; the fix is two lines when the module is next
  touched.
- **P3 `core/config.py:1281-1282`** — the cache publishes the fingerprint *before* the value, so a reader
  between the two stores can get a stale config. Requires an env change in a multithreaded process.
- **P3 `runtime/artifacts.py`** — `_registry_family_key` ignores the glob, so two registries sharing an
  `output_dir` consume each other's throttle counter; and the docstring's "up to 2049" bound is wrong for
  the batch (segment) writer, where the peak is `cap + interval − 1 + batch`. The 2000/30-day contract and
  the round-5 concurrency protection were both verified intact.
- **P3 `ui/application_flow.py:130-175`** — `build_in_memory_uploaded_file_fn` is assigned and never used;
  a test injecting it is green while production ignores it. Also, restart records created before spec 045
  are now rejected and self-deleted with only a log line — the user loses restart with no explanation.
- **P3** `SessionStateLike` promises only `get`/`__getitem__`/`__setitem__` but the code assigns attributes.
- **Product decision, not a defect — `document/roles.py`.** Spec 046 removed length-only heading promotion
  (correctly, per Constitution VII), but on PDF-derived books the remaining path is a **complete no-op**:
  `processing_runtime.py` never writes `run.font.size` into the intermediate DOCX, so `font_size_pt` is
  always `None` and the surviving evidence rule cannot fire. The golden fixtures lost **46** `role: heading`
  entries and gained none, among them real in-chapter subheadings. Spec 049 measured the obvious remedy
  (carry font size through PDF import) and disproved it: 0 recovered, 1 lost. Whether to accept this as the
  PDF ceiling or to look for a different heading signal is an owner decision, not a merge blocker.
- **Operational note.** `reader_cleanup_default = true` now genuinely enables the reader-cleanup pass in the
  interactive UI (spec 047 fixed the dead toggle). The repository's own `.env` carries
  `DOCX_AI_READER_CLEANUP_ENABLED=true`, so on this machine the pass becomes active after this merge, with
  the extra LLM cost and the deferred-DOCX build path that implies. `.env.example` ships `false`.

## SaaS rationale

Both P1 and the diagnostics P2 are multi-tenant hazards, not just local annoyances: the first turns a
delivered, already-paid-for document into an invitation to re-run it, and the second lets a run whose
identity threading broke score a perfect formatting verdict while its delivery gate silently stops
enforcing. Ownership-scoped evidence is only worth what its failure signal is worth.
