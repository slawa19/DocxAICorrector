# Reader Cleanup Model Strategy Experiments

Date: 2026-05-30
Status: Active experiment log and strategy plan
Owner surface: Reader cleanup runtime and reader verifier evidence

## Primary Task To Keep In View

We are not trying to find any model that can finish the current small chapter-region cleanup. The real product task is larger:

- process full books, not short excerpts;
- keep Gemini as the literary translation model because it currently produces good translation quality;
- use advanced text models for reader cleanup and verification where they add judgement: page furniture, fused headings, fragmented paragraphs, duplicate fragments, captions, and reader-visible structural defects;
- make the strategy scale to larger books by controlling prompt shape, chunk size, overlap, progress, retries, and artifact capture;
- preserve the architecture boundary: validation/verifier only observes and reports; runtime reader cleanup owns every mutation.

This means a model that is high quality but slow, such as direct Anthropic Claude, is still valuable if the cleanup strategy feeds it bounded, structured, overlapping work instead of one huge global prompt.

## Non-Negotiable Architecture Rules

- Gemini remains the translation baseline unless translation-quality evidence says otherwise.
- Reader cleanup remains AI-first: the model proposes bounded operations, runtime validates ids/hashes/exact substrings and applies safe operations.
- Verifier remains observer-only: it may score, classify, recommend anchors, and write evidence, but it must not mutate Markdown, rebuild DOCX, or apply cleanup.
- Do not solve cleanup by document-specific regex repair, phrase lists, or hardcoded Lietaer strings.
- Do not treat TOC page-number fidelity as a target. Stale page numbers can be ignored or removed only through reader cleanup policy when they harm reading.
- Every experiment must write a durable artifact set and a row in this document or a follow-up results table before conclusions are trusted.

## Current Evidence Snapshot

### Provider Integration

Direct Anthropic provider is implemented and smoke-tested.

- SDK dependency: `anthropic>=0.69.0`
- Config provider: `[providers.anthropic]`
- API key env: `ANTHROPIC_API_KEY`
- Working model id returned by Anthropic API: `claude-sonnet-4-6`
- Failed direct id: `claude-sonnet-4-6-20260217` returned `404 model not found`
- Direct smoke result: `OK`

Unit checks after provider work:

- `bash scripts/test.sh tests/test_config.py -q --tb=short` -> `80 passed`
- `bash scripts/test.sh tests/test_generation.py -q --tb=short` -> `65 passed`

Caveat: local worktree was dirty during these checks, so they are local proof for the touched provider/generation path, not CI proof for a clean checkout.

### Full Frozen Input Shape

Latest frozen raw Markdown used for replay:

- `.run/ui_results/20260530_102025_Rethinking-money-chapter-region-pages-10-11-and-156-217.raw.result.md`
- chars: `114894`
- blocks: `311`
- current cleanup chunking at `30000` chars yields approximately 4 chunks: `29876`, `29991`, `29473`, `25548`

### OpenRouter Claude Result

OpenRouter Claude Sonnet 4.6 did not complete the full cleanup replay usefully.

- Selector tested: `openrouter:anthropic/claude-sonnet-4.6`
- Input: same 114894-char frozen raw Markdown
- Symptom: only copied `.result.docx` existed; cleanup report/cleaned Markdown/review/summary were not written before stop/timeout.
- Interpretation: not a verifier failure and not a selector typo; it stalls before cleanup returns artifacts.

### Direct Anthropic Full Replay Result

Direct Anthropic reached provider/model/auth successfully, but the full replay still did not reach cleanup artifacts within a practical wait.

- Cleanup selector: `anthropic:claude-sonnet-4-6`
- Verifier selector: `anthropic:claude-sonnet-4-6`
- Input: same 114894-char frozen raw Markdown
- Experiment dir: `.run/reader_cleanup_replay_experiments/20260530T080816Z_direct-anthropic-current/`
- Symptom: only copied `.result.docx` appeared; no cleanup report/cleaned Markdown/review/summary before stop.
- Interpretation: direct Anthropic works technically, but the current full-input cleanup/global-plan call shape is too heavy.

### Direct Anthropic Bounded Cleanup Result

Direct Anthropic cleanup works on a bounded first-40-block probe.

- Probe input: `.run/ui_results/anthropic_reader_cleanup_probe_first40.raw.result.md`
- chars: `10171`
- blocks: `40`
- Experiment dir: `.run/reader_cleanup_replay_experiments/20260530T081037Z_direct-anthropic-first40/`
- Summary: `.run/reader_cleanup_replay_experiments/20260530T081037Z_direct-anthropic-first40/experiment_summary.md`
- Cleanup report: `.run/reader_cleanup_replay_experiments/20260530T081037Z_direct-anthropic-first40/anthropic-reader-cleanup-probe-first40/current/anthropic-reader-cleanup-probe-first40.current.r01of01.reader_cleanup_report.json`

Cleanup result:

- `stage_status`: `completed`
- `changed`: `true`
- raw blocks: `40`
- raw chars: `10171`
- cleanup chunks: `1`
- failed chunks: `0`
- proposed operations: `6`
- accepted operations: `3`
- accepted operation counts: `normalize_heading_boundary=2`, `split_block=1`
- ignored operations: `3`
- broad unsafe `remove_inline_noise` proposals: `0`

Accepted improvements included:

- separate `СТРАТЕГИИ ДЛЯ ГОСУДАРСТВ` from epigraph text;
- separate the Nietzsche attribution from body text;
- separate `ГРАЖДАНСКАЯ ВАЛЮТА: ЭКОНОМИЧЕСКИЙ СТИМУЛ БЕЗ ДОЛГОВ` from its body paragraph.

### Direct Anthropic Verifier Result

Direct Anthropic verifier works on the bounded cleanup artifacts when base artifacts are present.

Verifier-only artifact dir:

- `.run/reader_cleanup_replay_experiments/20260530T081037Z_direct-anthropic-first40/anthropic-verifier-only/`
- Review Markdown: `.run/reader_cleanup_replay_experiments/20260530T081037Z_direct-anthropic-first40/anthropic-verifier-only/anthropic-verifier-probe-first40_reader_quality_review.md`
- Review JSON: `.run/reader_cleanup_replay_experiments/20260530T081037Z_direct-anthropic-first40/anthropic-verifier-only/anthropic-verifier-probe-first40_reader_quality_review.json`

Verifier result:

- `verifier_status`: `completed`
- `verifier_provider`: `anthropic`
- `verifier_model_id`: `claude-sonnet-4-6`
- `overall_verdict`: `cleaned_better`
- `cleaned_audit_verdict`: `improved_but_has_remaining_issues`
- `confidence`: `high`
- raw score: `6.0`
- cleaned score: `7.0`
- remaining issues: `2`

Remaining issues identified:

- `fragmented_paragraph`: orphan duplicate sentence fragment beginning `деньги на другие нужды...`
- `orphan_caption`: standalone `Фото: Instituto Jaime Lerner.` line with no image context

The verifier also respected the observer-only boundary:

- `validator_boundary.observer_only = true`
- `runs_cleanup_repair = false`
- `mutates_cleaned_markdown = false`
- `mutates_cleaned_docx = false`
- `rebuilds_docx = false`

## What We Learned

1. Direct Anthropic is technically viable: key, SDK, provider selector, model id, request routing, cleanup call, and verifier call all work.
2. Direct Anthropic is slower and more sensitive to oversized prompt shape than Gemini.
3. The current bulk cleanup design is the wrong shape for full-book Anthropic cleanup: full raw global-plan context plus large chunks is too coarse.
4. Anthropic produces useful reader-quality judgement when the prompt is bounded: it separated real heading/body/epigraph boundaries and produced a high-confidence verifier review.
5. The right question is no longer `Gemini or Anthropic?`; it is `which model/strategy pairing gives the best quality per bounded unit of book-scale work?`
6. We need experiment logging that compares both model and strategy, not isolated ad hoc runs.

## Strategy Options To Test

| Strategy ID | Cleanup model | Verifier model | Chunk shape | Global plan | Expected use |
| --- | --- | --- | --- | --- | --- |
| `anthropic_small_overlap_v1` | `anthropic:claude-sonnet-4-6` | `anthropic:claude-sonnet-4-6` | 5k-10k target chars with overlap/context windows | disabled or compact per-window plan | First workable Anthropic cleanup baseline |
| `anthropic_anchor_repair_v1` | `anthropic:claude-sonnet-4-6` | `anthropic:claude-sonnet-4-6` | verifier/pre-audit anchors with local before/after context | none | Repair high-value defects after bulk cleanup |
| `gemini_bulk_anthropic_verifier_v1` | current Gemini cleanup selector | `anthropic:claude-sonnet-4-6` | current 30k chunks | current | Control/baseline, not final answer to the large-doc strategy problem |
| `hybrid_gemini_then_anthropic_anchor_v1` | Gemini bulk, Anthropic targeted repair | Anthropic | bulk then anchors | compact | Practical production candidate if full Anthropic remains slow |
| `anthropic_hierarchical_summary_v1` | Anthropic | Anthropic | small overlapping chunks plus rolling document outline | compact rolling summary only | Candidate for full-book cleanup with structure continuity |

## Recommended Next Direction

Start with `anthropic_small_overlap_v1`, not another full 115k replay and not a return to Gemini bulk cleanup.

Why:

- It directly addresses the primary task: making advanced text models usable on larger books.
- It keeps Anthropic in the cleanup role, where we want to test its textual judgement.
- It reduces prompt size, adds overlap, and preserves local structure, which is the same broad scaling principle used for translation.
- It gives us a reusable strategy for books larger than the current chapter region.

The first working Anthropic strategy should change shape, not just timeout:

- target cleanup chunk size: start with `8000` chars;
- overlap/context: include previous and next block windows, not duplicated mutation authority over the same blocks;
- global plan: disable the full raw global plan for Anthropic, or replace it with a compact per-window plan;
- progress: write per-chunk progress/artifacts so a slow model does not look hung;
- result safety: runtime still applies operations only to primary chunk block ids, not overlap-only context blocks;
- verifier: run Anthropic verifier after cleanup artifacts exist;
- result log: every run writes summary JSON/MD and this experiment doc gets a new row.

## Result Logging Contract

Every model/strategy experiment must record:

- date/time and run label;
- input artifact path;
- input char count and block count;
- cleanup selector and verifier selector;
- chunk target size and overlap size/window;
- global plan mode;
- repeat count;
- completion status;
- duration if available;
- cleanup stats: failed chunks, proposed/accepted/ignored operations, accepted operation counts;
- verifier stats: status, verdict, confidence, raw score, cleaned score, remaining issue count/categories;
- artifact paths: summary, cleanup report, cleaned Markdown, verifier review JSON/MD;
- interpretation: what this run proves and what it does not prove.

## Experiment Results Table

| Date | Strategy | Input | Size | Cleanup | Verifier | Status | Key result | Artifacts |
| --- | --- | --- | ---: | --- | --- | --- | --- | --- |
| 2026-05-30 | `openrouter_claude_bulk_current` | `20260530_102025...raw.result.md` | 114894 chars / 311 blocks | `openrouter:anthropic/claude-sonnet-4.6` | same | stopped/no cleanup artifacts | OpenRouter Claude did not return cleanup artifacts on full bulk shape | output dir only had copied DOCX |
| 2026-05-30 | `direct_anthropic_bulk_current` | `20260530_102025...raw.result.md` | 114894 chars / 311 blocks | `anthropic:claude-sonnet-4-6` | same | stopped/no cleanup artifacts | Direct Anthropic works technically but full bulk cleanup shape is too heavy | `.run/reader_cleanup_replay_experiments/20260530T080816Z_direct-anthropic-current/` |
| 2026-05-30 | `direct_anthropic_first40_current` | `anthropic_reader_cleanup_probe_first40.raw.result.md` | 10171 chars / 40 blocks | `anthropic:claude-sonnet-4-6` | attempted in replay; base artifacts initially missing | cleanup completed | 3 accepted operations, 0 failed chunks, useful heading/epigraph separation | `.run/reader_cleanup_replay_experiments/20260530T081037Z_direct-anthropic-first40/experiment_summary.md` |
| 2026-05-30 | `direct_anthropic_verifier_first40` | completed first40 cleanup artifacts | 40-block cleanup output | n/a | `anthropic:claude-sonnet-4-6` | completed | `cleaned_better`, confidence high, raw 6.0 -> cleaned 7.0, 2 remaining issues | `.run/reader_cleanup_replay_experiments/20260530T081037Z_direct-anthropic-first40/anthropic-verifier-only/anthropic-verifier-probe-first40_reader_quality_review.md` |
| 2026-05-25 | `gemini_current_baseline` | `20260525_185154...raw.result.md` | chapter-region input | `openrouter:google/gemini-3-flash-preview` | same | completed, 3 repeats | Current Gemini cleanup completed reliably but left 29, 32, and 32 remaining issues; mean 31.0; heading_fused_with_body 11-15; 1 broad unsafe remove_inline_noise proposal per repeat | `.run/reader_cleanup_replay_experiments/20260525T163254Z_fixed185154-current/experiment_summary.json` |
| 2026-05-25 | `gemini_decomposition_first_baseline` | `20260525_185154...raw.result.md` | chapter-region input | `openrouter:google/gemini-3-flash-preview` | same | completed, 3 repeats | Best historical Gemini cleanup baseline by remaining issues: 26, 33, and 26; mean 28.333; no broad unsafe remove_inline_noise proposals, but high cleanup variability remains | `.run/reader_cleanup_replay_experiments/20260525T163257Z_fixed185154-decomposition/experiment_summary.json` |
| 2026-05-25 | `gemini_anchor_focused_baseline` | `20260525_185154...raw.result.md` | chapter-region input | `openrouter:google/gemini-3-flash-preview` | same | completed, 3 repeats | Gemini anchor-focused left 26, 32, and 32 remaining issues; mean 30.0; did not beat decomposition_first and still left fused headings/page furniture | `.run/reader_cleanup_replay_experiments/20260525T163300Z_fixed185154-anchor/experiment_summary.json` |
| 2026-05-30 | `anthropic_small_overlap_v1` | `20260530_102025...raw.result.md` | 114894 chars / 311 blocks | `anthropic:claude-sonnet-4-6` | same | completed with partial cleanup failures | 15 chunks at 8000 chars, 3/3 read-only overlap, global plan disabled; 3 chunks failed on empty/non-JSON model response; 41 accepted operations; verifier completed with `cleaned_better`, confidence high, 18 remaining issues | `.run/reader_cleanup_replay_experiments/20260530T085112Z_anthropic-small-overlap-v1/experiment_summary.md` |
| 2026-05-30 | `anthropic_small_overlap_v1_json_extract` | `20260530_102025...raw.result.md` | 114894 chars / 311 blocks | `anthropic:claude-sonnet-4-6` | same | completed | Added strict JSON prompt/payload contract plus JSON-object extraction for prose-wrapped responses; 15 chunks, 0 failed chunks, 49 accepted operations, 0 broad unsafe remove_inline_noise proposals; verifier completed with `cleaned_better`, confidence high, 17 remaining issues | `.run/reader_cleanup_replay_experiments/20260530T093243Z_anthropic-small-overlap-v1-json-extract/experiment_summary.md` |
| 2026-05-30 | `gemini_small_overlap_v1_json_extract_control` | `20260530_102025...raw.result.md` | 114894 chars / 311 blocks | `openrouter:google/gemini-3-flash-preview` | same | completed with partial cleanup failures | Same input and same shape as stabilized Anthropic: 15 chunks at 8000 chars, 3/3 read-only overlap, global plan disabled; 2 chunks failed on schema validation/repair; 36 accepted operations; verifier completed with `cleaned_better`, confidence high, 27 remaining issues; issue counts: heading_fused_with_body 12, page_furniture_inline 2, broken_list_marker 11, fragmented_paragraph 2, mixed_language_leak 0; 0 broad unsafe remove_inline_noise proposals | `.run/reader_cleanup_replay_experiments/20260530T101736Z_gemini-small-overlap-v1-json-extract-control/experiment_summary.md` |
| 2026-05-30 | `anthropic_small_overlap_pr_h0a_inline_marker_duplicate_boundary_proof` | `20260530_102025...raw.result.md` | 114894 chars / 311 blocks | `anthropic:claude-sonnet-4-6` | same | completed | Runtime proof for inline marker and adjacent duplicate phrase contracts: 15 chunks, 0 failed chunks, 49 accepted operations, `noise_substring_not_found=0`, verifier `cleaned_better` high confidence, 17 remaining issues; inline endnote marker proof case closed, duplicate heading runtime-covered but not selected by model in this replay | `.run/reader_cleanup_replay_experiments/20260530T133307Z_anthropic-small-overlap-pr-h0a-inline-marker-duplicate-boundary-proof/experiment_summary.md` |
| 2026-05-30 | `anthropic_small_overlap_pr_h0b_targeting_proof` | `20260530_102025...raw.result.md` | 114894 chars / 311 blocks | `anthropic:claude-sonnet-4-6` | same | completed | Advisory `operation_selection_targets` proof: duplicate semantic heading selected and accepted as `remove_inline_noise`/`duplicate_fragment`; 15 chunks, 0 failed chunks, 52 accepted operations, verifier `cleaned_better` high confidence, 19 remaining issues; side-heading islands still produced rejected `remove_inline_noise_not_exact_noise_pattern` proposals | `.run/reader_cleanup_replay_experiments/20260530T155633Z_anthropic-small-overlap-pr-h0b-targeting-proof/experiment_summary.md` |
| 2026-05-30 | `anthropic_small_overlap_pr_h0c_side_heading_salience_proof` | `20260530_102025...raw.result.md` | 114894 chars / 311 blocks | `anthropic:claude-sonnet-4-6` | same | completed | Side-heading operation-choice salience proof: examples moved to accepted `split_block` instead of rejected semantic `remove_inline_noise`; 15 chunks, 0 failed chunks, 55 accepted operations, verifier `cleaned_better` high confidence, 20 remaining issues; success on operation choice, but new stub/continuation fragments remain | `.run/reader_cleanup_replay_experiments/20260530T165518Z_anthropic-small-overlap-pr-h0c-side-heading-salience-proof/experiment_summary.md` |
| 2026-05-31 | `anthropic_small_overlap_pr_h0d_side_heading_stub_continuation_proof_v2` | `20260530_102025...raw.result.md` | 114894 chars / 311 blocks | `anthropic:claude-sonnet-4-6` | same | completed with safety signal | Bounded `extract_side_heading_and_reattach_body` proof: 15 chunks, 0 failed chunks, 55 accepted operations, including 2 accepted side-heading reattach operations; verifier `cleaned_better` high confidence, 18 remaining issues; single heading-island sentence interruptions improved, but heading stacks still leave orphan continuations and 1 broad unsafe `remove_inline_noise` proposal was rejected by runtime | `.run/reader_cleanup_replay_experiments/20260531T131419Z_anthropic-small-overlap-pr-h0d-side-heading-stub-continuation-proof-v2/experiment_summary.md` |

## Gemini vs Anthropic Comparison

The current evidence does not support the claim that a simple one-for-one model swap is enough, but the same-input/same-shape control now shows Anthropic has a real cleanup-quality lead under the bounded strategy.

- Direct Anthropic on the old bulk/current shape did not produce cleanup artifacts on the 114894-char frozen input. This means the plain replacement `Gemini current -> Anthropic current` is not operationally viable for this document size.
- Anthropic became viable only after the request shape changed: 8000-char primary chunks, 3/3 read-only overlap, disabled full global plan, strict JSON contract, JSON extraction, and one retry for empty/non-JSON responses.
- The same-shape Gemini control used `openrouter:google/gemini-3-flash-preview` for both cleanup and verifier because that is the reader-cleanup Gemini baseline used by the historical runs. The translation default in `config.toml` is currently `openrouter:google/gemini-3.1-flash-lite-preview`; this control intentionally did not change production defaults or switch to that translation model.

Same-input, same-shape control:

| Metric | Anthropic stabilized | Gemini same-shape control |
| --- | ---: | ---: |
| cleanup chunks | 15 | 15 |
| failed chunks | 0 | 2 |
| accepted operations | 49 | 36 |
| verifier verdict | `cleaned_better`, high | `cleaned_better`, high |
| remaining issues | 17 | 27 |
| heading_fused_with_body | 4 | 12 |
| page_furniture_inline | 1 | 2 |
| broken_list_marker | 10 | 11 |
| fragmented_paragraph | 2 | 2 |
| mixed_language_leak | 0 | 0 |
| broad unsafe remove_inline_noise proposals | 0 | 0 |

Interpretation:

- The old conclusion remains true: the improvement is not `model selector only`, because Anthropic fails operationally on the old bulk prompt shape.
- The same-shape control adds a stronger conclusion: with the same input and same small-overlap shape, Anthropic is still materially better than Gemini on this artifact: 17 vs 27 remaining issues and 4 vs 12 fused-heading issues.
- Gemini's `failed_chunk_count=2` matters. The Gemini comparison is not just lower cleanup quality; it also shows weaker schema/contract reliability under the same shape. The failed chunks were 7 (`b_000125`-`b_000139`) and 9 (`b_000156`-`b_000175`), both from schema validation/repair failures on missing `evidence_before` fields.
- Historical Gemini baselines remain useful context but are no longer the fair control. They show Gemini usually leaves roughly 26-33 remaining issues on similar chapter-region artifacts; the same-shape control confirms the gap on the exact 20260530 frozen input.

Canonical shape decision:

- Treat the small-overlap form as the reader-cleanup canonical request shape across models: `chunk_size=8000`, `overlap_blocks_before=3`, `overlap_blocks_after=3`, `global_plan_enabled=false`.
- Do not increase chunk size in the immediate PR. The strongest completed run has 0 failed chunks at 8000 chars, while larger/bulk request shapes already failed operationally for Anthropic. A larger chunk may improve cross-boundary context, but it also increases malformed/empty response risk and reduces model portability.
- If tuning is needed, test it as a separate experiment matrix after the blind-spot PR: keep 8000 as control, try 10000/12000 only with the same frozen input, same model selectors, same verifier policy, and require `failed_chunk_count=0` before comparing quality scores.

Residual issue classes not fully surfaced by either cleanup path:

- Side-heading islands are now surfaced and operation-choice salience works for some proof examples: PR-H0c moved `Три мультинациональные валюты`, `Авиационные бонусные программы`, and `Частные международные расчетные единицы` to accepted `split_block` operations. PR-H0d added a bounded `extract_side_heading_and_reattach_body` operation for the narrower case where one semantic heading island interrupts one sentence, and the v2 replay accepted it for 2 proof sites. The remaining side-heading issue is the heading-stack/body-continuation class, where multiple heading-like islands precede a continuation that may need a separate contract or product limitation.
- Duplicate or repeated semantic heading text is closed for the proof site after PR-H0b: `Во многих странах национальные валюты Национальные валюты...` is selected as `remove_inline_noise` with reason `duplicate_fragment` and no longer remains in the cleaned proof artifact.
- Inline endnote-like markers were closed by PR-H0a for the proof case: `Однако в 1950-х годах 5 эта чеканка была запрещена.` now becomes `Однако в 1950-х годах эта чеканка была запрещена.` without word-boundary collapse. Keep this class monitored, but it is no longer the next PR-H target.
- The leading dash continuation artifact `— Эти монеты чеканились в Китае...` remains in both outputs. Anthropic mentions it only as a risk; Gemini does not surface it. It likely needs either merge-with-previous evidence or an explicit continuation-artifact category.

PR-H0a proof update:

- Proof artifact: `.run/reader_cleanup_replay_experiments/20260530T133307Z_anthropic-small-overlap-pr-h0a-inline-marker-duplicate-boundary-proof/`.
- Result: `15` chunks, `0` failed chunks, `49` accepted operations, `22` accepted `remove_inline_noise`, verifier `cleaned_better` high confidence, raw `4.0` -> cleaned `6.0`, `17` remaining issues, `noise_substring_not_found=0`, broad unsafe remove_inline_noise proposals `0`.
- Result after PR-H0b targeting: `.run/reader_cleanup_replay_experiments/20260530T155633Z_anthropic-small-overlap-pr-h0b-targeting-proof/`, `15` chunks, `0` failed chunks, `52` accepted operations, verifier `cleaned_better` high confidence, `19` remaining issues; duplicate semantic heading targeting worked, but side-heading islands still fell back to rejected `remove_inline_noise`.
- Result after PR-H0c side-heading salience: `.run/reader_cleanup_replay_experiments/20260530T165518Z_anthropic-small-overlap-pr-h0c-side-heading-salience-proof/`, `15` chunks, `0` failed chunks, `55` accepted operations, verifier `cleaned_better` high confidence, `20` remaining issues; side-heading operation choice improved to accepted `split_block`, but the split result leaves orphan sentence stubs/continuations.
- Result after PR-H0d side-heading stub/continuation contract: `.run/reader_cleanup_replay_experiments/20260531T131419Z_anthropic-small-overlap-pr-h0d-side-heading-stub-continuation-proof-v2/`, `15` chunks, `0` failed chunks, `55` accepted operations, including `2` accepted `extract_side_heading_and_reattach_body` operations; verifier `cleaned_better` high confidence, `18` remaining issues. This proves the new bounded operation for single heading-island sentence interruptions, but it is not an MVP exit proof because heading-stack continuations remain and the run still had `1` broad unsafe `remove_inline_noise` proposal rejected by runtime.
- Next direction: a narrow semantic-title/page-heading deletion salience slice before repeat stability or third-model bakeoff. The runtime safety backstop works, but the model should stop proposing section-title-like text as `remove_inline_noise`.

Conclusion: keep Gemini as the literary translation baseline. For reader cleanup, treat the Anthropic small-overlap path as the current quality leader, with PR-H0b/PR-H0c evidence showing that advisory targeting can change operation selection and PR-H0d evidence showing that a new bounded operation can improve a specific side-heading continuation defect. Do not switch production cleanup defaults yet; the next decision should be based on closing the remaining safety signal and heading-stack/body-continuation class before repeat stability, cost/latency comparison, or another broad model bakeoff.

## First Implementation Slice: Workable Anthropic Cleanup

Goal: make Anthropic cleanup complete on the existing 114894-char frozen input by changing chunk strategy, not by increasing timeout.

Implemented in the current MVP, without a new strategy framework:

- `ReaderCleanupConfig` now carries `overlap_blocks_before`, `overlap_blocks_after`, and `global_plan_enabled` alongside the existing `chunk_size`.
- Cleanup chunks keep primary `blocks` as the only editable targets; overlap blocks are sent as `readonly_context_blocks_before` / `readonly_context_blocks_after`.
- Runtime validation ignores operations that target read-only overlap block ids with `ignored_reason=readonly_context_block`.
- Cleanup reports and replay summaries now include model selector, chunk size, overlap before/after, global-plan mode, cleanup chunk count, and failed chunk count.
- Replay CLI now accepts `--cleanup-chunk-size`, `--cleanup-overlap-blocks-before`, `--cleanup-overlap-blocks-after`, and `--cleanup-global-plan-enabled`.
- Replay accepts a frozen input basename from `.run/ui_results/` and writes a per-run `.progress.json`.
- Follow-up hardening records failed chunk diagnostics with block id range, model selector, approximate prompt/input size, raw response preview, empty-response flag, parse error, retry status, and repair status.
- Empty/non-JSON cleanup responses are retried once; prose-wrapped JSON objects are extracted and parsed while the prompt/payload contract still requires JSON only with no markdown fences or surrounding prose.

Command used for the first large-input Anthropic run:

```bash
PYTHONPATH=.:src python tests/artifacts/real_document_pipeline/run_reader_cleanup_replay_experiment.py \
  --inputs 20260530_102025_Rethinking-money-chapter-region-pages-10-11-and-156-217.raw.result.md \
  --strategies current \
  --repeats 1 \
  --cleanup-model-selector anthropic:claude-sonnet-4-6 \
  --verifier-model-selector anthropic:claude-sonnet-4-6 \
  --max-retries 1 \
  --label anthropic-small-overlap-v1 \
  --cleanup-chunk-size 8000 \
  --cleanup-overlap-blocks-before 3 \
  --cleanup-overlap-blocks-after 3 \
  --cleanup-global-plan-enabled false
```

Proposed slice:

1. Add an experiment-only cleanup chunking mode with smaller primary chunks and overlap context.
2. Primary chunk owns mutation targets; overlap is read-only context.
3. Disable full raw global plan for this strategy or replace it with a compact per-window plan.
4. Start with `target_chars=8000`, `overlap_blocks_before=3`, `overlap_blocks_after=3`.
5. Run on the same frozen `20260530_102025...raw.result.md` input.
6. Persist per-chunk progress after every model call.
7. Run Anthropic verifier on completed artifacts.
8. Add the run to the Experiment Results Table.

Success criteria for the first slice:

- cleanup replay completes on the 114894-char input;
- `failed_chunk_count = 0`;
- cleanup report and cleaned Markdown are written;
- verifier reaches `verifier_status=completed`;
- no false deletion or validation boundary violation is reported;
- result is good enough to compare against current Gemini/baseline evidence.

## Open Questions

- Best initial Anthropic chunk target: `5000`, `8000`, or `10000` chars?
- Should overlap be block-count based, char-window based, or semantic-boundary based?
- Should the global plan be fully disabled for Anthropic, or replaced with a compact plan built from deterministic pre-audit findings?
- Should targeted repair run immediately after the first cleanup pass or only after verifier/pre-audit produces anchors?
- Which additional models should enter the bake-off after Anthropic has one working large-input strategy?
