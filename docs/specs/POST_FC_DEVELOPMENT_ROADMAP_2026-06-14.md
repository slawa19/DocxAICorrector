# Post-FC Development Roadmap

Date: 2026-06-14
Status: Active roadmap for the implementing agent
Owner surface: whole pipeline (import -> translate -> cleanup -> rebuild ->
restore -> validate), proof harness, corpus
Reviewer: plan author reviews each work-stream result and returns findings.
Related (read before starting):
`docs/specs/FORMATTING_COVERAGE_CONSOLIDATION_PLAN_2026-06-13.md`,
`docs/specs/SIMPLE_READER_FIRST_MVP_REPAIR_PR_BACKLOG_2026-05-23.md`,
`docs/specs/PDF_TEXT_LAYER_SOURCE_IMPORT_PIVOT_SPEC_2026-06-01.md`,
`docs/specs/READER_CLEANUP_MODEL_STRATEGY_EXPERIMENTS_2026-05-30.md`

## Product Goal (the thing all work serves)

Translate **full books** (PDF -> translated DOCX) preserving formatting, images,
structure, and reading quality, at book scale. Gemini stays the translation
baseline; advanced models do reader cleanup where judgement helps. Everything
below is judged by whether it moves the product toward full-book output, not by
how perfect one chapter excerpt looks.

## Where We Are (entry state, 2026-06-14)

- Translation, reader cleanup (PR-H0 readable-draft boundary), PDF text-layer
  import, image preservation (12/12), and id-first lineage all work.
- The long-standing formatting blocker (PR-I2) is **code-complete**: the gate is
  now role-aware coverage (heading/list/caption role loss counts; body
  legitimately dissolved into a body neighbor with evidence is credited), shared
  between production `validation/structural.py` and the proof runner via
  `validation/formatting_coverage.py`.
- A no-LLM restore replay exists (`validation/formatting_replay.py`) — use it.
- Mapping ceiling: `mapped=89`, raw `29/36` unmapped before role-aware
  accounting; residual dominated by dissolved/aggregate, not lost formatting.
- **Not done:** the FC iteration's final live proof (blocked locally on optional
  `pdfminer.six`). The whole role-aware reframe is validated on **one** document
  (Lietaer chapter-region) only.

## Working Rules (non-negotiable — these are the lessons of the last iteration)

1. **Large chunks, not micro-slices.** Each work-stream below is one substantial
   unit. Do not split a work-stream into a dozen "hypothesis confirmed" proofs.
2. **Deterministic results, recorded as measured numbers — never "confirmed".**
   A chunk is done only when its verifiable result is in the doc with the actual
   numbers from a run, not intentions.
3. **Use the no-LLM replay for the inner loop.** Reserve full LLM proof runs for
   genuine behaviour validation. Do not burn a translation run to read
   deterministic diagnostics.
4. **Always run the FULL relevant test file(s), never only focused selectors.**
   The 54-test regression slipped through because only new tests were run.
5. **Production and harness share logic.** No gate/credit that lives only in the
   proof runner. If the product should enforce it, it lives in `src/`.
6. **Named result types over positional tuples** for any multi-field return.
7. **Content-presence != format-presence.** Never credit a source as covered
   because its text survived if its structural role was lost.
8. **No document-specific literals, no new broad substring/containment matcher
   heuristics, no verifier as a gate.**

## How This Will Be Reviewed

After each work-stream the agent reports: what changed (files), the measured
verifiable result, the full-file test results, and any deviation from scope with
its justification. The reviewer checks the result against the "Verifiable result"
and "Done" lines below and returns findings before the next work-stream starts.

---

# WS-1. Close & Archive the FC Iteration

**Goal:** discharge the one remaining FC gate and archive the spec.

**Scope:**
- Install optional `pdfminer.six` in the environment.
- Run one chapter-region live proof with current code.
- Confirm: role-aware basis appears in the gate, the run produces an artifact
  containing `final_generated_paragraph_registry`, images stay 12/12, output DOCX
  opens, exactly one restore pass (single build).
- Move `FORMATTING_COVERAGE_CONSOLIDATION_PLAN_2026-06-13.md` to an archive
  location/status once the proof passes.

**Verifiable result:**
- A fresh run dir whose report has `unmapped_source_count_basis =
  role_aware_formatting_coverage`, a non-empty
  `/runtime/state/final_generated_paragraph_registry`, `formatting_diagnostics`
  length `1`, images 12/12.
- The role-aware effective unmapped number recorded, with the residual either
  empty or a hand-checkable list of real heading/list/caption role losses.

**Guardrails / non-goals:** no code changes beyond what the proof needs; if the
proof reveals a real bug, stop and report rather than patching blind.

**Done:** proof artifact recorded with the numbers above; FC spec archived.

# WS-2. Generalize the Role-Aware Gate Beyond One Document

**Goal:** prove the role-aware reframe holds on more than the single excerpt
before trusting it as the product gate.

**Scope:**
- Run the role-aware gate on at least 2-3 other corpus profiles (e.g.
  first-20-pages, full-benchmark), using the no-LLM replay where a saved final
  DOCX exists and fresh runs only where needed.
- For each: record raw vs role-aware effective unmapped, the credited
  (body-dissolved) set, and the real-loss (heading/list/caption -> body) set.
- **Manually spot-check** a sample of credited items: is each genuinely covered,
  or is the fuzzy evidence over-crediting? Tune the evidence threshold
  (measurement-only) if false credit is found.

**Verifiable result:**
- A cross-document table: per document, raw `unmapped_*`, role-aware effective,
  credited count, real-loss count, false-credit count from the spot-check.
- A written conclusion: does role-aware generalize, and what evidence threshold
  is safe across documents (not tuned to one).

**Guardrails / non-goals:** measurement-only changes to evidence; do not relax
the gate by asserting coverage without spot-check proof; do not tune to a single
document.

**Done:** role-aware gate validated (or corrected) on >=3 documents with a
documented safe threshold and zero unexplained false credits.

# WS-3. Full-Book End-to-End Run

**Goal:** move from excerpt to a full book — the actual product target.

**Scope:**
- Take one full book through the complete pipeline (import -> translate ->
  cleanup -> single rebuild/restore -> validate) with verifier off.
- Exercise book scale: chunking, progress/artifact capture per stage, retries,
  and record wall-clock + cost.
- Catalogue every failure mode that appears at scale (translation aborts,
  empty_response, memory, time, malformed chunks) — do not fix them inline;
  record them for WS-4.

**Verifiable result:**
- A completed full-book run that produces an openable final DOCX, images
  preserved, and a role-aware gate result recorded for the whole book.
- A failure-mode catalogue with frequency and stage for each issue.
- Runtime and approximate cost recorded.

**Guardrails / non-goals:** do not regress the chapter-region result; do not
introduce per-document hacks to force a book through; if a stage cannot complete,
record the controlled failure, do not silently truncate output.

**Done:** one full book produces a complete artifact set with the gate result and
a failure-mode catalogue.

# WS-4. Reliability Hardening At Book Scale (driven by WS-3)

**Goal:** make a full-book run survive its own failure modes.

**Scope:** address the WS-3 catalogue in priority order. Likely: persistent
`empty_response` recovery at scale (is PR-R0 enough across hundreds of blocks?),
bounded retries, controlled per-block fallback artifacts instead of whole-run
aborts, and progress that lets a long run be observed/resumed.

**Verifiable result:**
- A full-book run with **zero uncontrolled pipeline aborts**; any block that
  cannot be translated produces an explicit fallback artifact/event, and the run
  still finishes with a complete document.
- Before/after the hardening: failure count from WS-3 -> after.

**Guardrails / non-goals:** do not change the translation model/prompt or reader
cleanup behaviour; reliability only. No silent data loss — every fallback is
visible in artifacts.

**Done:** a full book completes end-to-end with no uncontrolled abort and all
failures surfaced as artifacts.

# WS-5. Tooling & Process Hardening (cross-cutting, ongoing)

**Goal:** keep the cheap, honest feedback loop that the last iteration painfully
earned.

**Scope:**
- Extend the no-LLM replay so the full role-aware/coverage diagnostic set can be
  recomputed offline from any saved run (close the stale-artifact fidelity gap
  where it matters).
- A dev/CI contract that runs full relevant test files, not focused selectors.
- Audit remaining multi-field positional returns in the pipeline and convert the
  fragile ones to named results.

**Verifiable result:**
- Replay reproduces the role-aware effective number for a saved run within a
  stated tolerance, no model call.
- Test contract documented/enforced; positional-return audit list with
  conversions done for the fragile ones.

**Guardrails / non-goals:** tooling only; no behavioural change to the product
pipeline.

**Done:** offline replay covers the role-aware metric; full-file test discipline
enforced; fragile returns converted.

---

# Sequencing

1. **WS-1** first (close the open iteration; small).
2. **WS-2** next (trust the gate beyond one document before scaling on it).
3. **WS-3** (the product goal: full book) — the largest chunk.
4. **WS-4** falls out of WS-3 and is driven by its catalogue.
5. **WS-5** runs alongside, prioritised whenever the inner loop gets expensive or
   a regression slips through.

Do not start WS-3 before WS-2 confirms the gate generalises — otherwise a
book-scale run is measured by a gate trusted on one excerpt.
