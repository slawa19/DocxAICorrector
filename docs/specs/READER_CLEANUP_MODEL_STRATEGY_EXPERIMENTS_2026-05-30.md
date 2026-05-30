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
| 2026-05-30 | `anthropic_small_overlap_v1` | `20260530_102025...raw.result.md` | 114894 chars / 311 blocks | `anthropic:claude-sonnet-4-6` | same | completed with partial cleanup failures | 15 chunks at 8000 chars, 3/3 read-only overlap, global plan disabled; 3 chunks failed on empty/non-JSON model response; 41 accepted operations; verifier completed with `cleaned_better`, confidence high, 18 remaining issues | `.run/reader_cleanup_replay_experiments/20260530T085112Z_anthropic-small-overlap-v1/experiment_summary.md` |

## First Implementation Slice: Workable Anthropic Cleanup

Goal: make Anthropic cleanup complete on the existing 114894-char frozen input by changing chunk strategy, not by increasing timeout.

Implemented in the current MVP, without a new strategy framework:

- `ReaderCleanupConfig` now carries `overlap_blocks_before`, `overlap_blocks_after`, and `global_plan_enabled` alongside the existing `chunk_size`.
- Cleanup chunks keep primary `blocks` as the only editable targets; overlap blocks are sent as `readonly_context_blocks_before` / `readonly_context_blocks_after`.
- Runtime validation ignores operations that target read-only overlap block ids with `ignored_reason=readonly_context_block`.
- Cleanup reports and replay summaries now include model selector, chunk size, overlap before/after, global-plan mode, cleanup chunk count, and failed chunk count.
- Replay CLI now accepts `--cleanup-chunk-size`, `--cleanup-overlap-blocks-before`, `--cleanup-overlap-blocks-after`, and `--cleanup-global-plan-enabled`.
- Replay accepts a frozen input basename from `.run/ui_results/` and writes a per-run `.progress.json`.

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
