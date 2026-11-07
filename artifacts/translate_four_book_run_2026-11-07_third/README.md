# Four-book translate, third run (spec 064 FR-010) — baseline → after-063 → third (2026-11-07/08)

The four corpus books, translated en → ru through the production `translate` path on `0babd1c` (spec 064: run
context and glossary delivered into the system prompt, gate exclusions for policy-kept apparatus, region credit for
list-fragment residue, model-kept citations relabelled, figure-cell import rule, glossary collision/name rules).
Same profile as the two earlier runs, `ui-parity-translate-benchmark-advisory-image-safe-no-cleanup`, same model
`openrouter:google/gemini-3.1-flash-lite-preview`, one book at a time via `scripts/run-real-document-validation.sh`
under WSL. Run ids `20261107T_fidelity3_translate_<slug>`.
Earlier runs: baseline `artifacts/translate_four_book_run_2026-11-07/` (`f4d5562`), after-063
`artifacts/translate_four_book_run_2026-11-07_after/` (`aca048a`).

This folder keeps only each run's `run_summary.txt` and `result_notices.json`.

**Where the material is.** Delivered DOCX/Markdown, full logs, full reports, aligned pairs, glossary artifacts,
fallback artifacts, the three-way comparison (`COMPARISON.md`, `comparison.json`, `COMPARISON_notes.md`) and the
scripts that produced it are in `D:\Temp\docxai-runs\2026-11-07-translate-third\` (WSL
`/mnt/d/Temp/docxai-runs/2026-11-07-translate-third/`), **outside the repository and not versioned**.

## Per book (third run)

| | Money | CW | RM | VoE |
|---|---:|---:|---:|---:|
| result | succeeded | succeeded | succeeded | succeeded |
| delivery disposition | accepted_with_advisory (after-063: **blocked**) | accepted_with_advisory | accepted_with_advisory | accepted_with_advisory |
| acceptance_passed | **True** | False | **True** | **True** |
| failed checks | — | `list_fragment_regressions_present` | — | — |
| translation_quality_status | warn | warn | warn | warn |
| model calls | 293 | 401 | 245 | 693 |
| cost, $ (provider-reported) | 0.4786 | 0.5894 | 0.5044 | 0.8770 |
| … glossary, $ | 0.0138 | 0.0079 (**failed**) | 0.0136 | 0.0128 |
| prompt / completion tokens | 1 342 832 / 155 943 | 1 360 369 / 173 502 | 1 256 692 / 173 502 | 3 130 518 / 227 833 |
| duration, s | 588.6 | 782.4 | 620.4 | 1 164.6 |
| `system_prompt_chars` / context chars | 12 519 / 4 646 | 8 680 / 807 | 13 207 / 5 334 | 12 694 / 4 821 |
| prompt tokens per text call, after-063 → third | 2 960 → 4 533 | 2 845 → 3 388 | 3 213 → 5 076 | 3 023 → 4 489 |
| own-glossary adherence, after-063 → third | 66.1 → 77.6 % | 73.6 % → — (no glossary) | 60.2 → 71.5 % | 62.7 → 73.6 % |
| reviewers' terms with ≤ 1 rendering (063 SC-006) | 8/22 | 0/16 | 8/17 | 12/20 |
| number tokens created/deleted by assembly | 0/0 | 0/0 | 0/0 | 0/0 |
| footnote markers kept (source = delivered) | 236 = 236 | 152 = 152 | 229 = 229 | 381 = 381 |
| controlled-fallback blocks (after-063) | 2 (1) | 0 (0) | 1 (1) | **6** (209) |
| `omitted` pairs (after-063) | 0 (0) | 0 (1) | 0 (0) | 0 (1) |
| policy_kept_source pairs: without a call / by the model | 23 / 1 | 0 / 97 | 101 / 59 | 212 / 349 |

## Totals

| | baseline | after-063 | third |
|---|---:|---:|---:|
| model calls | 1 922 | 1 680 | 1 632 |
| cost, $ | 2.634 | 2.386 | 2.449 |
| … glossary, $ | 0 | 0.057 | 0.048 |
| prompt tokens | 4 980 749 | 5 119 349 | 7 090 411 |
| duration, s | 3 739 | 3 287 | 3 156 |

## Spec 064 success criteria, live

- SC-001 (context reaches the model): met on Money, RM, VoE (+1 466…1 863 prompt tokens per call, forecast
  +1 500…2 200); on CW only the 807-char plan arrived because the glossary failed.
- SC-002 (Money delivered): **met** — untranslated body 19 027 chars → 0, not blocked.
- SC-003 (`list_fragment_regressions_present` passes on CW/RM/VoE): RM, VoE pass; **CW fails** on one sample.
- SC-004 (VoE controlled fallback ≤ 10): **met** — 209 → 6 blocks, all torn citations.
- SC-006 (own glossary ≥ 85 %): **not met** — 77.6 / — / 71.5 / 73.6 %; 063 SC-006 (≥ 90 % of key terms with ≤ 1
  rendering) 36 / 0 / 47 / 60 %.
- Manual read: 0 commentary paragraphs among 91 model-kept `policy_kept_source` paragraphs (Money 1, CW/RM/VoE 30 each).

## Unexpected

1. **CW glossary failed** (`IncompleteResponse`, 4 436 completion tokens against the 4 440 cap of call A,
   `src/docxaicorrector/text/glossary_pass.py:975-976`, `:1028-1035`); a call-A failure ends the phase without retry
   (`src/docxaicorrector/pipeline/glossary_phase.py:639-647`), so CW was translated with no terms or names.
2. **CW `list_fragment_regressions_present`**: one uncredited sample, `delivered.md:3487` — the second half of note 8
   (source p1781/p1782, split mid-sentence on import: the R-7 pair), now translated rather than `omitted`; it and its
   neighbours carry no reference signal, so the region credit
   (`src/docxaicorrector/pipeline/quality_gate.py:610-683`) does not apply. Replayed offline on this run's inputs.
3. RM: one mixed back-matter block (0 → 1); 16 references translated (was 1), 24 echoed and relabelled.
4. VoE `context_leakage` retries 24 → 32 (baseline 11).
5. VoE `value -> стоимость` entry is followed hard (ch. 8 стоимость/ценность 11/32 → 32/10, ch. 9 1/19 → 21/1);
   correctness in the public-value chapters is for the reader review (063 SC-007).
6. Cache hits are not recorded by the pipeline; the third-run text stage is cheaper than list price by
   $0.09 / $0.01 / $0.07 / $0.25, consistent with implicit caching of the system prompt (inferred, not reported).

Full detail, every table and the method: `D:\Temp\docxai-runs\2026-11-07-translate-third\COMPARISON.md`.
