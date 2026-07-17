# Feature Specification: Caption→heading delivery gate must see the FINAL (post reader-cleanup) DOCX diagnostics

Date: 2026-07-17
Status: **PLANNED (2026-07-17).** Round-9 P1 (+ related P2). Spec-042 P1-B wired a caption→heading
conflict to the delivery gate, but only for the NON-deferred DOCX path. When reader cleanup is enabled the
base DOCX is built LATE, so the gate runs on an EMPTY / stale formatting-diagnostics list and a caption
conflict introduced by the FINAL DOCX escapes the gate and publishes. Verified against live code by the
orchestrator. This is already on `main` (PR #4 merged); fix lands on `fix/round9-reader-cleanup-caption-gate`
and is PR'd back.

## P1 — reader-cleanup deferred build: the gate uses stale/empty formatting diagnostics

**Verified flow (`pipeline/late_phases.py`, `pipeline/reader_cleanup_postprocess.py`,
`pipeline/reader_cleanup_rebuild.py`):**
- `should_defer_base_docx_build = _should_run_reader_cleanup(...)` (`late_phases.py:465`). When true the base
  DOCX is NOT built at `:475-476`, so `docx_bytes is None` and `formatting_diagnostics_artifacts` stays
  `[]` (`:507-512`). The FIRST (pre-cleanup) quality gate therefore runs on an EMPTY diagnostics list.
- Reader cleanup then builds the FINAL DOCX (`late_phases.py:726-742`): the no-change path calls
  `base_docx_builder()` (`reader_cleanup_postprocess.py:316`), the change path calls
  `_rebuild_docx_for_markdown` (`:366` → `reader_cleanup_rebuild.py:85`
  `dependencies.preserve_source_paragraph_properties(...)`). BOTH write FRESH formatting-diagnostics
  artifacts (incl. `caption_heading_conflicts`) to `diagnostics_dir`.
- The post-cleanup report rebuild (`late_phases.py:784-809`) (a) runs ONLY when
  `runtime_display_markdown != pre_reader_cleanup_display_markdown`, and (b) even then passes the STALE
  pre-cleanup `formatting_diagnostics_artifacts` (`:788`, `:803`) — the empty list. So a caption→heading
  conflict in the FINAL DOCX is never gated: with markdown unchanged the gate is not re-run at all, and with
  markdown changed it is re-run against an empty diagnostics list.

**Fix:**
1. After the final DOCX is known (after `final_docx_bytes = reader_cleanup_postprocess.docx_bytes`,
   `late_phases.py:742`), and WHENEVER the base build was deferred (reader cleanup ran + produced a DOCX),
   RE-COLLECT fresh diagnostics: `post_cleanup_formatting_diagnostics_artifacts =
   collect_recent_formatting_diagnostics_artifacts(since_epoch_seconds=build_started_at_epoch,
   diagnostics_dir=diagnostics_dir)` — this now includes the final-DOCX artifacts written during the
   reader-cleanup build.
2. Use `post_cleanup_formatting_diagnostics_artifacts` (not the stale pre-cleanup list) wherever the
   post-cleanup report/verdict is built (`:788`, `:803`).
3. The caption→heading delivery gate must run on the FINAL diagnostics EVEN WHEN the markdown is unchanged
   (the deferred base build still produced a DOCX + diagnostics the pre-cleanup gate never saw). Decouple
   the caption-conflict re-check from the `markdown-changed` rebuild trigger: when the base build was
   deferred and the re-collected diagnostics carry a caption→heading conflict, ensure `quality_status`
   becomes `"fail"` + a `caption_heading_conflict` gate_reason so delivery is blocked (route into the
   existing `late_phases.py:664` fail path). Do NOT otherwise rebuild the full report on unchanged markdown
   (keep the byte-identical-when-unchanged behavior for everything EXCEPT the now-authoritative caption
   gate). The cleanest implementation: when deferred, always resolve the caption-conflict count from the
   re-collected FINAL diagnostics and feed it into the gate that decides `quality_status`.

## P2 — delivery gate reads only the LAST diagnostics artifact; acceptance sums ALL

**Verified:** `quality_gate.py:1211-1217` computes `caption_heading_conflict_count` from a single
`latest_payload` (the last artifact), whereas `build_acceptance_verdict` aggregates
`total_caption_heading_conflicts` across ALL formatting-diagnostics payloads
(`acceptance.py` formatting loop). With multiple artifacts present the delivery gate can under-count and
diverge from the acceptance verdict ("acceptance failed" but delivery succeeds).

**Fix:** in the delivery gate, aggregate caption→heading conflicts across ALL current diagnostics artifacts
(mirroring the acceptance verdict's total) rather than the last artifact only — OR define one authoritative
FINAL diagnostics artifact and gate on it consistently with acceptance. Keep the aggregation keyed on the
conflict signal only (no per-book literal). The delivery gate and the acceptance verdict must agree on the
conflict count for the same run.

## Non-goals

- NO change to the warn/advisory behavior of unmapped coverage (specs 038/039).
- NO change to the non-deferred (no reader cleanup) path — spec-042 P1-B already gates it correctly.
- NO rebuild of the full quality report on unchanged markdown beyond what the caption gate strictly needs.

## Anti-regression (mandatory)

- **The round-9 regression test:** `reader_cleanup_enabled` + a FINAL DOCX (built during reader cleanup)
  that carries a caption→heading conflict → `result == "failed"`, a `caption_heading_conflict` gate reason,
  `quality_status == "fail"`, and primary UI artifacts / `.result.*` are NOT written. Cover BOTH the
  markdown-changed and markdown-unchanged reader-cleanup sub-paths (the unchanged path is the one the
  current code misses entirely).
- A reader-cleanup run with NO caption conflict still publishes (behavior unchanged; unchanged-markdown stays
  byte-identical for the non-caption path).
- The non-deferred path (spec-042 test) stays green.
- P2: a synthetic run with multiple diagnostics artifacts, a conflict only in a non-last artifact → the
  delivery gate still fails (matches acceptance).
- Full no-LLM suite green; pyright ≤246; CI green (watched).

## SaaS rationale

Closes the real hole where a caption→heading structural defect introduced (or first surfaced) by the
reader-cleanup-built FINAL DOCX would publish despite spec-042 P1-B — the gate must judge the delivered
artifact, not a stale pre-cleanup snapshot — and aligns the delivery gate's conflict count with the
acceptance verdict's.
