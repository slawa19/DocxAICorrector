# Four-book translate rerun after spec 063 — before → after (2026-11-07)

The four corpus books, rerun through the production `translate` path (en → ru, DOCX) on `main` = `aca048a`
(spec 063: list-fragment carry fix, footnote markers at import and restoration, headings at import,
apparatus policy by region, per-run glossary). Same profile as the baseline,
`ui-parity-translate-benchmark-advisory-image-safe-no-cleanup`, same model
`openrouter:google/gemini-3.1-flash-lite-preview`, one book at a time via
`scripts/run-real-document-validation.sh` under WSL. Run ids `20261107T_fidelity2_translate_<slug>`.
Baseline: `artifacts/translate_four_book_run_2026-11-07/` (`f4d5562`).

This folder keeps only each run's `run_summary.txt` and `result_notices.json`
(`runtime.state.latest_result_notices`, `latest_result_notice`, `latest_delivery_disposition`, the
controlled-fallback artifact path, the acceptance verdict).

**Where the material is.** Delivered DOCX/Markdown, full logs, full reports, aligned pairs, glossary artifacts,
the comparison (`COMPARISON.md`, `comparison.json`) and the scripts that produced it are in
`D:\Temp\docxai-runs\2026-11-07-translate-after\` (WSL `/mnt/d/Temp/docxai-runs/2026-11-07-translate-after/`).
That folder is **outside the repository and not versioned**. The baseline material is in
`D:\Temp\docxai-runs\2026-11-07-translate\`.

Every cell below is `before → after`.


### Pairing

| | Money | CW | RM | VoE |
|---|---:|---:|---:|---:|
| pairs | 1371 → 1373 | 1782 → 1787 | 1844 → 1855 | 2180 → 2153 |
| before pairs → of them mapped to an after pair | 1371 → 1316 | 1782 → 1702 | 1844 → 1766 | 2180 → 2074 |
| after final registry basis | state → replay | state → state | state → state | state → state |

### 1. Delivered-text drift (non-merged paragraphs; registry level)

| | Money | CW | RM | VoE |
|---|---:|---:|---:|---:|
| delivered text ≠ model output | 10 → 1 | 24 → 0 | 87 → 0 | 100 → 3 |
| … gained a leading `N. ` | 9 → 0 | 14 → 0 | 87 → 0 | 58 → 1 |
| … gained a leading `YYYY. ` | 4 → 0 | 14 → 0 | 84 → 0 | 13 → 0 |
| number tokens created (P0) | 5 → 0 | 10 → 0 | 56 → 0 | 52 → 0 |
| number tokens deleted (P0) | 0 → 0 | 0 → 0 | 16 → 0 | 1 → 0 |
| rule (e): pair target opens with `N.` not from its source | 10 → 0 | 21 → 0 | 117 → 0 | 108 → 1 |
| double ordinals (pairs) | 0 → 0 | 8 → 0 | 0 → 0 | 39 → 0 |
| double ordinals (`delivered.md` lines) | 0 → 0 | 8 → 0 | 0 → 0 | 39 → 0 |

### 2. Paragraph boundaries and headings

| | Money | CW | RM | VoE |
|---|---:|---:|---:|---:|
| merged pairs | 45 → 40 | 34 → 27 | 138 → 120 | 108 → 97 |
| merged pairs that are headings | 3 → 2 | 3 → 2 | 9 → 8 | 2 → 0 |
| source headings (pairs) | 169 → 175 | 238 → 245 | 146 → 166 | 128 → 129 |
| delivered `#` lines (pairs) | 165 → 172 | 234 → 243 | 137 → 158 | 125 → 128 |
| source headings delivered without `#` | 4 → 3 | 4 → 2 | 9 → 8 | 3 → 1 |

### 3. Footnote references (superscript-digit runs per pair)

| | Money | CW | RM | VoE |
|---|---:|---:|---:|---:|
| source paragraphs with markers | 158 → 174 | 132 → 132 | 167 → 179 | 209 → 285 |
| marker runs: source | 215 → 236 | 152 → 152 | 214 → 229 | 252 → 381 |
| marker runs: model output | 215 → 242 | 152 → 157 | 199 → 236 | 251 → 404 |
| marker runs: delivered | 215 → 242 | 152 → 157 | 199 → 236 | 251 → 404 |
| kept by the model (share of source) | 0.9628 → 1 | 0.9671 → 1 | 0.8972 → 1 | 0.8968 → 1 |
| kept in delivery (share of source) | 0.9628 → 1 | 0.9671 → 1 | 0.8972 → 1 | 0.8968 → 1 |
| paragraphs losing a marker in delivery | 7 → 0 | 4 → 0 | 14 → 0 | 20 → 0 |
| run counter: source / kept / restored / delivered (after) | — → 236/236/0/236 | — → 152/152/0/152 | — → 229/229/0/229 | — → 381/381/0/381 |

### 4. Apparatus policy

| | Money | CW | RM | VoE |
|---|---:|---:|---:|---:|
| blocks kept in source without a model call | — → 7 | — → 0 | — → 3 | — → 45 |
| paragraphs kept (policy_kept_source) | — → 25 | — → 0 | — → 120 | — → 307 |
| chars kept | — → 33731 | — → 0 | — → 11632 | — → 37687 |
| mixed back-matter blocks | — → 1 | — → 0 | — → 0 | — → 0 |
| back matter delivered as source, per section | — → {"references": 26} | — → {"notes": 143} | — → {"index": 36, "notes": 47, "references": 176} | — → {"notes": 413, "references": 309} |
| back matter translated, per section | — → {"references": 10} | — → {"notes": 99} | — → {"index": 395, "notes": 218, "references": 1} | — → {"notes": 274, "references": 1} |
| controlled-fallback pairs | 2 → 2 | 0 → 0 | 55 → 1 | 68 → 312 |
| controlled-fallback blocks | 1 → 1 | 0 → 0 | 2 → 1 | 49 → 209 |
| `omitted` pairs (after: delivered in English) | — → 0 | — → 1 | — → 0 | — → 1 |

### 5a. Run glossary (after only)

| | Money | CW | RM | VoE |
|---|---:|---:|---:|---:|
| status | — → built | — → built | — → built | — → built |
| terms in glossary | — → 148 | — → 138 | — → 160 | — → 148 |
| rendered into the prompt | — → 120 | — → 110 | — → 132 | — → 98 |
| required candidates | — → 93 | — → 80 | — → 110 | — → 89 |
| optional candidates | — → 304 | — → 320 | — → 290 | — → 311 |
| name entries | — → 31 | — → 46 | — → 27 | — → 29 |
| prompt section chars (cap) | — → 3953 (4000) | — → 3991 (4000) | — → 3972 (4000) | — → 3996 (4000) |
| glossary model calls | — → 3 | — → 2 | — → 3 | — → 3 |
| glossary cost, $ | — → 0.0146 | — → 0.0129 | — → 0.0148 | — → 0.0145 |
| target collisions found / resolved | — → 4/3 | — → 0/0 | — → 3/1 | — → 1/1 |

### 5b. Terminology — reviewers' term lists, same method both sides, all pairs in scope

| | Money | CW | RM | VoE |
|---|---:|---:|---:|---:|
| terms with occurrences | 22 → 22 | 16 → 16 | 17 → 17 | 20 → 20 |
| terms with ≤ 1 rendering | 4 → 5 | 0 → 0 | 3 → 5 | 8 → 8 |
| mean distinct renderings per term | 2.36 → 2.27 | 7.38 → 7.5 | 2.41 → 2.35 | 1.85 → 1.85 |

### 6. Cost and calls

| | Money | CW | RM | VoE |
|---|---:|---:|---:|---:|
| model calls | 360 → 298 | 470 → 419 | 335 → 275 | 757 → 688 |
| cost, $ (provider-reported) | 0.538802 → 0.461906 | 0.58577 → 0.563964 | 0.540436 → 0.494076 | 0.96869 → 0.865749 |
| … of which glossary, $ | 0 → 0.0146 | 0 → 0.0129 | 0 → 0.0148 | 0 → 0.0145 |
| prompt tokens | 910313 → 902266 | 1122152 → 1213765 | 850031 → 903203 | 2098253 → 2100115 |
| completion tokens | 179035 → 158169 | 175948 → 174597 | 191683 → 180679 | 259034 → 227147 |
| duration, s | 798.224 → 622.806 | 811.022 → 795.054 | 830.317 → 678.508 | 1299.079 → 1190.595 |
| jobs (blocks) | 338 → 340 | 443 → 449 | 305 → 319 | 706 → 706 |
| source paragraphs | 1426 → 1420 | 1829 → 1823 | 2265 → 2254 | 2295 → 2258 |
| retries | 15 → 5 | 5 → 9 | 16 → 9 | 23 → 38 |

### 7. Acceptance and delivery

| | Money | CW | RM | VoE |
|---|---:|---:|---:|---:|
| result | succeeded → failed | succeeded → succeeded | succeeded → succeeded | succeeded → succeeded |
| acceptance_passed | True → False | True → False | False → False | True → False |
| failed checks | none → pipeline_succeeded,translation_quality_report_not_failed | none → list_fragment_regressions_present,key_headings_preserved | untranslated_prose_not_delivered → list_fragment_regressions_present,untranslated_prose_not_delivered | none → list_fragment_regressions_present |
| translation_quality_status | pass → fail | warn → warn | warn → warn | warn → warn |

### Totals

| | before | after |
|---|---:|---:|
| model calls | 1922 | 1680 |
| cost, $ | 2.6337 | 2.3857 |
| … glossary, $ | 0 | 0.0569 |



## Findings in brief (details and file:line in `COMPARISON.md` of the durable folder)

- **Fixed as intended:** assembly creates and deletes no number token on any book (was 5/10/56/52 created);
  rule (e) prefixes 10/21/117/108 → 0/0/0/1 (the one is a correct carry of a note number); double ordinals
  8 (CW) and 39 (VoE) → 0; footnote markers kept 96.3/96.7/89.7/89.7 % → 100 % on all four (restoration fired 0
  times); VoE blocker 592 now reads «почти 30 000 фунтов… средний заработок.³⁹»; torn headings RM 411/546/578/740,
  CW 745 and VoE chapter 7 arrive whole; RM copyright page translated.
- **Money's result was blocked** (`result=failed`, delivery `blocked`): the document-level gate counted the
  25 reference paragraphs the apparatus policy keeps in English as untranslated body text
  (`untranslated_body_text_above_threshold`, 19 027 chars, 3.5 %), fatal on `translate`
  (`src/docxaicorrector/pipeline/quality_gate.py:185-187`, `:1716-1745`). All four flagged samples are
  `policy_kept_source` paragraphs.
- **No image-analysis call on any book** (before 43/62/55/42). Images still delivered in safe mode; most of the
  cost saving is this. Cause not investigated (spec 062 territory; `image/analysis.py:317` returns the heuristic
  silently when there is no client).
- **VoE notes:** 209 controlled-fallback blocks (before 49), the model echoing citation-only notes; notes go
  413 as source vs 274 translated — two policies in one section.
- **Acceptance:** `list_fragment_regressions_present` now fails CW, RM and VoE (gated count 1/0/3 → 11/2/42);
  CW also `key_headings_preserved` (one figure label imported as a heading, then demoted); RM still
  `untranslated_prose_not_delivered` (a 2-char unanchored fallback).
- **The glossary did not change term choices.** Adherence to each run's own glossary 69.1/75.4/61.2/68.1 % →
  66.1/73.6/60.2/62.7 %; terms with ≤ 1 rendering 4/0/3/8 → 5/0/5/8. The glossary itself maps
  `sustainability -> жизнеспособность` (Money), `Resilience -> живучесть` (RM, used in 0 of 18 pairs),
  `Lietaer -> Литар/Лита`, and has no `value` entry for VoE; the value split by chapter is unchanged.
