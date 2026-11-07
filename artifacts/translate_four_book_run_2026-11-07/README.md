# Translate run of the four corpus books for a translation-fidelity review — 2026-11-07

Four books through the production `translate` path (en → ru, DOCX output) on `main` = `f4d5562`,
run profile `ui-parity-translate-benchmark-advisory-image-safe-no-cleanup` (markers on,
image_mode safe, reader cleanup off, advisory gate), repo-default model
`openrouter:google/gemini-3.1-flash-lite-preview`. One book at a time, via
`scripts/run-real-document-validation.sh` under WSL Debian, from a side worktree.

This folder keeps only each run's `run_summary.txt` (the runner's `..._summary.txt`) and
`result_notices.json` (`runtime.state.latest_result_notices` plus `latest_result_notice`,
`latest_delivery_disposition`, the controlled-fallback artifact path and the acceptance verdict).

## Cost

| book | run id | calls | cost, $ | duration, s | acceptance |
|---|---|---:|---:|---:|---|
| Money & Sustainability | `20261107T_fidelity_translate_money_sustainability` | 360 | 0.5388 | 798 | passed |
| Creating Wealth | `20261107T_fidelity_translate_creating_wealth` | 470 | 0.5858 | 811 | passed |
| Rethinking Money | `20261107T_fidelity_translate_rethinking_money` | 335 | 0.5404 | 830 | failed: `untranslated_prose_not_delivered` |
| The Value of Everything | `20261107T_fidelity_translate_value_of_everything` | 757 | 0.9687 | 1299 | passed |
| **total** | | **1922** | **2.6337** | | |

All four runs finished with `result=succeeded` and exit 0. Cost is the provider-reported ledger
(`model_accounting_cost_usd_reported_by_provider`) and includes image analysis.

## Where the material is

The delivered DOCX/Markdown, full logs, aligned source/target paragraph pairs (`pairs.jsonl`),
per-book `stats.json` / `chapters.json`, the re-derived source paragraphs and the extraction
scripts are in `D:\Temp\docxai-runs\2026-11-07-translate\` (WSL
`/mnt/d/Temp/docxai-runs/2026-11-07-translate/`), starting from its `INDEX.md`. That folder is
**outside the repository and not versioned**; nothing in it is in git. The full run reports
(21–98 MB each) are copied there too, next to each book's pairs.
